import logging
import os

import psycopg

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
)

logger = logging.getLogger(__name__)


def record_pipeline_failure(context):
    task_instance = context["task_instance"]
    dag_run = context["dag_run"]
    exception = context.get("exception")
    logical_date = context.get("logical_date")

    dag_id = task_instance.dag_id
    task_id = task_instance.task_id
    run_id = dag_run.run_id
    error_message = str(exception) if exception else None

    logger.error(
        "Pipeline task failed: dag_id=%s task_id=%s run_id=%s error=%s",
        dag_id,
        task_id,
        run_id,
        error_message,
    )

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_failures (
                    dag_id,
                    task_id,
                    run_id,
                    logical_date,
                    error_message
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    dag_id,
                    task_id,
                    run_id,
                    logical_date,
                    error_message,
                ),
            )
