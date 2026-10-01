import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg
from faker import Faker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAYSIM_PATH = PROJECT_ROOT / "data" / "raw" / "PS_20174392719_1491204439457_log.csv"

SAMPLE_SIZE = 200_000
CHUNK_SIZE = 100_000
RANDOM_SEED = 42
BASE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)
DATABASE_URL = "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch"

Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)

fake = Faker("en_GB")


def load_paysim_sample(path: Path, sample_size: int) -> pd.DataFrame:
    chunk_sizes = [
        len(chunk)
        for chunk in pd.read_csv(
            path,
            usecols=["step"],
            chunksize=CHUNK_SIZE,
        )
    ]

    total_rows = sum(chunk_sizes)

    if sample_size > total_rows:
        raise ValueError(
            f"Requested {sample_size:,} rows, "
            f"but dataset only contained {total_rows:,} rows."
        )

    sampled_chunks = []
    rows_sampled = 0

    for chunk_number, chunk in enumerate(pd.read_csv(path, chunksize=CHUNK_SIZE)):
        if chunk_number == len(chunk_sizes) - 1:
            rows_to_sample = sample_size - rows_sampled
        else:
            rows_to_sample = round(sample_size * chunk_sizes[chunk_number] / total_rows)

        sampled = chunk.sample(
            n=rows_to_sample,
            random_state=RANDOM_SEED + chunk_number,
        )

        sampled_chunks.append(sampled)
        rows_sampled += len(sampled)

    sample = pd.concat(
        sampled_chunks,
        ignore_index=True,
    )

    return sample.sort_values(
        "step",
        kind="stable",
    ).reset_index(drop=True)


def get_unique_account_ids(transactions: pd.DataFrame) -> list[str]:
    senders = set(transactions["nameOrig"])
    receivers = set(transactions["nameDest"])

    return sorted(senders | receivers)


def generate_customers_and_accounts(
    account_ids: list[str],
) -> tuple[list[tuple], list[tuple]]:
    customers = []
    accounts = []

    now = datetime.now(UTC)

    for customer_id, account_id in enumerate(account_ids, start=1):
        opened_at = now - timedelta(days=random.randint(30, 3650))

        customers.append(
            (
                customer_id,
                fake.name(),
                fake.email(),
                fake.phone_number(),
                fake.address().replace("\n", ", "),
                fake.job(),
            )
        )

        accounts.append(
            (
                account_id,
                customer_id,
                opened_at,
            )
        )

    return customers, accounts


def prepare_transactions(
    transactions: pd.DataFrame,
) -> list[tuple]:
    rows = []

    for row in transactions.itertuples(index=False):
        timestamp = BASE_TIMESTAMP + timedelta(hours=int(row.step))

        rows.append(
            (
                row.nameOrig,
                row.nameDest,
                row.type,
                float(row.amount),
                timestamp,
                bool(row.isFraud),
            )
        )

    return rows


def reset_database(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            TRUNCATE TABLE
                audit_log,
                cases,
                alerts,
                transactions,
                accounts,
                customers
            RESTART IDENTITY CASCADE
            """
        )


def seed_database(
    customers: list[tuple],
    accounts: list[tuple],
    transactions: list[tuple],
) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        reset_database(connection)
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO customers (
                    id,
                    name,
                    email,
                    phone,
                    address,
                    occupation
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                customers,
            )

            cursor.executemany(
                """
                INSERT INTO accounts (
                    id,
                    customer_id,
                    opened_at
                )
                VALUES (%s, %s, %s)
                """,
                accounts,
            )

            cursor.executemany(
                """
                INSERT INTO transactions (
                    sender_account_id,
                    receiver_account_id,
                    transaction_type,
                    amount,
                    timestamp,
                    is_fraud
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                transactions,
            )

            cursor.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('customers', 'id'),
                    (SELECT MAX(id) FROM customers)
                )
                """
            )


if __name__ == "__main__":
    # 1. Load the PaySim development sample.
    transactions = load_paysim_sample(PAYSIM_PATH, SAMPLE_SIZE)

    # 2. Extract every unique sender and receiver account.
    account_ids = get_unique_account_ids(transactions)

    # 3. Generate synthetic customers and their accounts.
    customers, accounts = generate_customers_and_accounts(account_ids)

    # 4. Convert PaySim rows into our database transaction format.
    transaction_rows = prepare_transactions(transactions)

    # 5. Print counts so we can verify the pipeline.
    print(f"Transactions: {len(transactions):,}")
    print(f"Unique accounts: {len(account_ids):,}")
    print(f"Customers generated: {len(customers):,}")
    print(f"Accounts generated: {len(accounts):,}")
    print(f"Prepared transactions: {len(transaction_rows):,}")

    # 6. Inspect one example from each generated dataset.
    print("\nExample customer:")
    print(customers[0])

    print("\nExample account:")
    print(accounts[0])

    print("\nExample transaction:")
    print(transaction_rows[0])

    # 7. Seed PostgreSQL.
    print("\nSeeding PostgreSQL...")
    seed_database(customers, accounts, transaction_rows)
    print("Database seed complete.")
