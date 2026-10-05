from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, get_current_context, task

from pipeline.callbacks import record_pipeline_failure
from pipeline.ingest import ingest_landing_file
from pipeline.report import write_pipeline_run
from pipeline.tasks import (
    build_features_for_date,
    create_alerts_for_date,
    score_features_for_date,
)
from pipeline.validate import validate_staged_transactions


def get_run_date():
    context = get_current_context()
    dag_run = context["dag_run"]

    run_datetime = dag_run.logical_date or dag_run.run_after

    return run_datetime.date()


@dag(
    dag_id="mulewatch_daily",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    on_failure_callback=record_pipeline_failure,
    tags=["mulewatch"],
)
def mulewatch_daily():
    @task(execution_timeout=timedelta(minutes=5))
    def ingest():
        run_date = get_run_date()
        row_count = ingest_landing_file(run_date)

        return {
            "run_date": run_date.isoformat(),
            "rows_ingested": row_count,
        }

    @task(
        execution_timeout=timedelta(minutes=5),
        retries=0,
    )
    def validate():
        run_date = get_run_date()
        clean_count, quarantine_count = validate_staged_transactions(run_date)

        return {
            "run_date": run_date.isoformat(),
            "clean_count": clean_count,
            "quarantine_count": quarantine_count,
        }

    @task(execution_timeout=timedelta(minutes=10))
    def features():
        run_date = get_run_date()

        return build_features_for_date(run_date)

    @task(
        execution_timeout=timedelta(minutes=10),
        retries=3,
        retry_delay=timedelta(seconds=30),
        retry_exponential_backoff=True,
    )
    def score():
        run_date = get_run_date()

        return score_features_for_date(run_date)

    @task(execution_timeout=timedelta(minutes=5))
    def alerts():
        run_date = get_run_date()

        return create_alerts_for_date(run_date)

    @task(execution_timeout=timedelta(minutes=5))
    def report(
        ingest_metadata,
        validate_metadata,
        score_metadata,
        alert_metadata,
    ):
        context = get_current_context()
        dag_run = context["dag_run"]

        run_date = get_run_date()

        started_at = dag_run.start_date

        duration_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()

        return write_pipeline_run(
            run_date=run_date,
            rows_in=ingest_metadata["rows_ingested"],
            rows_quarantined=validate_metadata["quarantine_count"],
            accounts_scored=score_metadata["scored_count"],
            alerts_raised=alert_metadata["alerts_selected"],
            model_version=score_metadata["model_version"],
            duration_seconds=duration_seconds,
        )

    ingest_result = ingest()
    validate_result = validate()
    features_result = features()
    score_result = score()
    alerts_result = alerts()

    ingest_result >> validate_result >> features_result >> score_result >> alerts_result

    report(
        ingest_result,
        validate_result,
        score_result,
        alerts_result,
    )


mulewatch_daily()
