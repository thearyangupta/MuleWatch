import os
from contextlib import contextmanager

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

CHECKPOINT_DATABASE_URL = os.getenv(
    "MULEWATCH_CHECKPOINT_DATABASE_URL",
    os.getenv(
        "MULEWATCH_CASE_DATABASE_URL",
        "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
    ),
)


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def initialize_checkpointer() -> None:
    """Create LangGraph checkpoint tables. Run once at setup."""
    with PostgresSaver.from_conn_string(CHECKPOINT_DATABASE_URL) as checkpointer:
        checkpointer.setup()


@contextmanager
def review_graph():
    """Keep the checkpoint connection alive for each invocation."""
    from agent.graph import build_graph

    with PostgresSaver.from_conn_string(CHECKPOINT_DATABASE_URL) as checkpointer:
        graph = build_graph(
            checkpointer=checkpointer,
            human_review=True,
        )
        yield graph
