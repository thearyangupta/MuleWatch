from datetime import datetime

from airflow.sdk import dag, get_current_context, task


def log_run_date(task_name: str) -> None:
    context = get_current_context()
    dag_run = context["dag_run"]

    run_date = dag_run.logical_date or dag_run.run_after

    print(f"{task_name}: logical_date={run_date}")


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
        log_run_date("ingest")

    @task
    def validate():
        log_run_date("validate")

    @task
    def features():
        log_run_date("features")

    @task
    def score():
        log_run_date("score")

    @task
    def alerts():
        log_run_date("alerts")

    ingest() >> validate() >> features() >> score() >> alerts()


mulewatch_daily()
