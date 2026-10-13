from pathlib import Path

import psycopg

from agent.graph import CASE_DATABASE_URL
from agent.review_runtime import initialize_checkpointer

migration = Path("db/review.sql").read_text(encoding="utf-8")

with psycopg.connect(CASE_DATABASE_URL) as connection:
    connection.execute(migration)

print("Case review schema migration complete.")

initialize_checkpointer()

print("LangGraph PostgreSQL checkpoint tables ready.")
