from pathlib import Path

from airflow.models import DagBag

DAG_ID = "mulewatch_daily"
DAG_FOLDER = Path(__file__).resolve().parents[1] / "dags"


def test_dag_imports_without_errors():
    dag_bag = DagBag(
        dag_folder=str(DAG_FOLDER),
    )

    assert dag_bag.import_errors == {}


def test_mulewatch_daily_has_expected_tasks():
    dag_bag = DagBag(
        dag_folder=str(DAG_FOLDER),
    )

    dag = dag_bag.get_dag(DAG_ID)

    assert dag is not None

    expected_task_ids = {
        "ingest",
        "validate",
        "features",
        "score",
        "alerts",
        "report",
    }

    assert set(dag.task_ids) == expected_task_ids


def test_mulewatch_daily_dependency_order():
    dag_bag = DagBag(
        dag_folder=str(DAG_FOLDER),
    )

    dag = dag_bag.get_dag(DAG_ID)

    expected_dependencies = {
        "ingest": {"validate", "report"},
        "validate": {"features", "report"},
        "features": {"score"},
        "score": {"alerts", "report"},
        "alerts": {"report"},
        "report": set(),
    }

    actual_dependencies = {
        task.task_id: {downstream.task_id for downstream in task.downstream_list}
        for task in dag.tasks
    }

    assert actual_dependencies == expected_dependencies
