from datetime import UTC, datetime, timedelta
from pathlib import Path

from pipeline.seed import SAMPLE_SIZE, load_paysim_sample

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PAYSIM_PATH = PROJECT_ROOT / "data" / "raw" / "PS_20174392719_1491204439457_log.csv"

LANDING_DIR = PROJECT_ROOT / "data" / "landing"

BASE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def simulated_date(step: int) -> str:
    day_index = min((int(step) - 1) // 24, 29)
    timestamp = BASE_TIMESTAMP + timedelta(days=day_index)
    return timestamp.date().isoformat()


def split_daily_files() -> None:
    LANDING_DIR.mkdir(parents=True, exist_ok=True)

    transactions = load_paysim_sample(
        PAYSIM_PATH,
        SAMPLE_SIZE,
    )

    transactions["landing_date"] = transactions["step"].apply(simulated_date)

    for landing_date, daily_rows in transactions.groupby(
        "landing_date",
        sort=True,
    ):
        output_path = LANDING_DIR / f"{landing_date}.csv"

        daily_rows = daily_rows.drop(columns=["landing_date"])

        daily_rows.to_csv(
            output_path,
            index=False,
        )

        print(f"{landing_date}: {len(daily_rows):,} rows -> {output_path.name}")


if __name__ == "__main__":
    split_daily_files()
