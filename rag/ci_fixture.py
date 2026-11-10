"""Synthetic retrieval corpus for isolated CI tests only.

These are original test descriptions, NOT extracts from the cited publications.
Never use this fixture in a production or genuine-source knowledge base.
"""

import os

import psycopg
from pgvector.psycopg import register_vector

from rag.ingest import (
    DATABASE_URL,
    create_typology_chunks_table,
    embed_chunks,
    load_embedding_model,
    store_chunks,
)
from rag.search import DATABASE_URL as SEARCH_DATABASE_URL

SYNTHETIC_SOURCE = "MuleWatch CI Synthetic Fixture"

DOCUMENTS = [
    (
        "Proceeds of fraud - Detecting and preventing money mules",
        "Rapid pass-through of funds through an account, money mule account "
        "detection systems, suspicious transaction monitoring and controls. "
        "Detecting proceeds of fraud requires checking unusual incoming "
        "payments and rapid outgoing transfers.",
    ),
    (
        (
            "Firms' use of the National Fraud Database (NFD) "
            "and money mule account detection tools"
        ),
        "Using fraud databases to identify mule accounts. National Fraud "
        "Database NFD records, account detection tools and fraud indicators "
        "can support financial crime investigations.",
    ),
    (
        "Money mules: mule activity and cashing out findings",
        "How criminals cash out money from mule accounts. Mule activity "
        "includes cash withdrawals, onward transfers and movement of "
        "fraudulent funds after receipt.",
    ),
    (
        "Money transfer scams",
        "Warning signs of money transfer scams include unexpected requests "
        "to send funds, impersonation, pressure and suspicious payment "
        "instructions.",
    ),
    (
        "Don't become a money mule: what you need to know",
        "Criminals recruit people to move illegal money using their bank "
        "accounts. Money mule recruitment can involve promises of easy "
        "earnings for transferring funds.",
    ),
    (
        "Money mules - what are the risks?",
        "Risks and consequences of acting as a money mule include "
        "criminal investigation, loss of banking access and legal "
        "consequences. Moving criminal proceeds is dangerous.",
    ),
    (
        "#YourAccountYourCrime: Global campaign exposes use of money mules",
        "Criminal networks recruiting money mules online may use social "
        "media messages and fake job offers. Online recruitment exposes "
        "people to financial crime networks.",
    ),
    (
        "Money mule and financial exploitation action plan",
        "Financial exploitation and recruitment of money mules can "
        "target vulnerable individuals. An action plan addresses "
        "prevention, safeguarding and financial exploitation.",
    ),
    (
        "MuleWatch Feature Definitions",
        "Pass-through ratio and dwell time account features measure "
        "how quickly incoming money leaves an account. Transaction "
        "features support mule account detection.",
    ),
]


def main():
    if os.getenv("MULEWATCH_CI_SYNTHETIC_CORPUS") != "1":
        raise RuntimeError("Synthetic corpus requires explicit CI opt-in.")

    if DATABASE_URL != SEARCH_DATABASE_URL:
        raise RuntimeError("Ingestion and retrieval database URLs differ.")

    with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:
        database_name = conn.execute("SELECT current_database()").fetchone()[0]

        if database_name not in {"mulewatch_test", "mulewatch_ci_validation"}:
            raise RuntimeError(f"Refusing synthetic ingestion into {database_name!r}")

        register_vector(conn)
        create_typology_chunks_table(conn)

        existing = conn.execute("SELECT COUNT(*) FROM typology_chunks").fetchone()[0]

        if existing:
            raise RuntimeError("CI retrieval corpus must start empty.")

        chunks = [
            {
                "chunk_id": f"ci_synthetic:{index}:1",
                "content": content,
                "source": SYNTHETIC_SOURCE,
                "title": title,
                "section": "Original synthetic test description",
                "url": None,
                "date": None,
            }
            for index, (title, content) in enumerate(DOCUMENTS, start=1)
        ]

        model = load_embedding_model()
        embed_chunks(chunks, model)
        store_chunks(chunks, conn)

    print(
        f"PASS: Inserted {len(chunks)} original synthetic "
        f"CI documents into isolated {database_name}."
    )


if __name__ == "__main__":
    main()
