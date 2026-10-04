from datetime import datetime

from airflow.sdk import dag, get_current_context, task

from pipeline.ingest import ingest_landing_file
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
    tags=["mulewatch"],
)
def mulewatch_daily():
    @task
    def ingest():
        run_date = get_run_date()

        row_count = ingest_landing_file(run_date)

        return {
            "run_date": run_date.isoformat(),
            "rows_ingested": row_count,
        }

    @task
    def validate():
        run_date = get_run_date()

        clean_count, quarantine_count = validate_staged_transactions(run_date)

        return {
            "run_date": run_date.isoformat(),
            "clean_count": clean_count,
            "quarantine_count": quarantine_count,
        }

    @task
    def features():
        run_date = get_run_date()

        return build_features_for_date(run_date)

    @task
    def score():
        run_date = get_run_date()

        return score_features_for_date(run_date)

    @task
    def alerts():
        run_date = get_run_date()

        return create_alerts_for_date(run_date)

    (ingest() >> validate() >> features() >> score() >> alerts())


mulewatch_daily()
