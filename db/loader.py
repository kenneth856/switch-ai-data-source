import logging
import os
import pandas as pd
from datetime import datetime
from db.client import get_client

logger = logging.getLogger(__name__)

RAW_DIR = "data/raw"


def _load_csv(filename: str) -> pd.DataFrame | None:
    path = os.path.join(RAW_DIR, filename)
    if not os.path.exists(path):
        logger.warning("[SKIP] %s not found — run extract.py first", filename)
        return None
    df = pd.read_csv(path)
    # Replace NaN with None so JSON serialisation works
    df = df.where(pd.notnull(df), None)
    return df


# Upsert all rows from df into the given Supabase table.
def _upsert(table: str, df: pd.DataFrame, conflict_col: str):
    client = get_client()
    records = df.to_dict(orient="records")

    # Supabase upsert in batches of 500 to avoid payload size limits
    batch_size = 500
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        client.table(table).upsert(batch, on_conflict=conflict_col).execute()
        total += len(batch)

    logger.info("[OK] %s — %d rows upserted", table, total)


def load_vendors():
    df = _load_csv("vendors.csv")
    if df is None:
        return
    _upsert("vendors", df, "id")


def load_items():
    df = _load_csv("items.csv")
    if df is None:
        return
    _upsert("items", df, "id")


def load_transactions():
    df = _load_csv("transactions.csv")
    if df is None:
        return
    _upsert("transactions", df, "id")


def load_transaction_lines():
    df = _load_csv("transaction_lines.csv")
    if df is None:
        return
    # transaction_lines has no single unique id — use composite key (transaction + linesequencenumber)
    # Supabase upsert needs a unique constraint on those columns in the DB
    _upsert("transaction_lines", df, "transaction,linesequencenumber")


def load_fuel_prices():
    df = _load_csv("fuel_prices.csv")
    if df is None:
        return
    # Normalise date to string for JSON
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    _upsert("fuel_prices", df, "date")


def load_exchange_rates():
    df = _load_csv("exchange_rates.csv")
    if df is None:
        return
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    _upsert("exchange_rates", df, "date")


def run():
    logger.info("=== Supabase Load Started: %s ===", datetime.now())

    logger.info("1. Loading vendors...")
    load_vendors()

    logger.info("2. Loading items...")
    load_items()

    logger.info("3. Loading transactions...")
    load_transactions()

    logger.info("4. Loading transaction lines...")
    load_transaction_lines()

    logger.info("5. Loading fuel prices...")
    load_fuel_prices()

    logger.info("6. Loading exchange rates...")
    load_exchange_rates()

    logger.info("=== Supabase Load Complete: %s ===", datetime.now())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    run()
