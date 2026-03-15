"""
SPRINT 1 — Task 1.4
Data pipeline: NetSuite → local data files → Supabase

This script pulls all needed data from NetSuite and saves it
as CSV files in data/raw/ for processing.

Run manually:   python -m pipeline.extract
Run in Docker:  docker exec ai-module python -m pipeline.extract
"""

import os
import logging
import pandas as pd
from datetime import datetime
from netsuite.client import run_suiteql
from pipeline.scrape_external import run as scrape_external
from db.loader import run as load_to_supabase
from netsuite.queries import (
    VENDOR_QUERY,
    ITEM_QUERY,
    TRANSACTION_QUERY,
    TRANSACTION_LINE_QUERY,
    FREIGHT_COST_QUERY,
    SLA_QUERY,
)

logger = logging.getLogger(__name__)
RAW_DIR = "data/raw"
os.makedirs(RAW_DIR, exist_ok=True)


def save(records: list, filename: str):
    if not records:
        logger.warning("No data returned for %s", filename)
        return
    df = pd.DataFrame(records)
    path = os.path.join(RAW_DIR, filename)
    df.to_csv(path, index=False)
    logger.info("Saved %d records → %s", len(df), path)


def run():
    logger.info("=== NetSuite Data Extraction Started: %s ===", datetime.now())

    logger.info("1. Pulling vendors...")
    save(run_suiteql(VENDOR_QUERY), "vendors.csv")

    logger.info("2. Pulling items / ingredients...")
    save(run_suiteql(ITEM_QUERY), "items.csv")

    logger.info("3. Pulling transactions...")
    save(run_suiteql(TRANSACTION_QUERY), "transactions.csv")

    logger.info("4. Pulling transaction lines...")
    save(run_suiteql(TRANSACTION_LINE_QUERY), "transaction_lines.csv")

    logger.info("5. Pulling freight cost history (PurchOrd)...")
    save(run_suiteql(FREIGHT_COST_QUERY), "freight_cost.csv")

    logger.info("6. Pulling SLA / delivery timeline data...")
    save(run_suiteql(SLA_QUERY), "sla_data.csv")

    logger.info("7. Pulling external market data (fuel, commodities, FX)...")
    scrape_external()

    logger.info("8. Loading all data to Supabase...")
    try:
        load_to_supabase()
    except RuntimeError as e:
        logger.warning("Supabase skipped: %s", e)

    logger.info("=== Extraction Complete: %s ===", datetime.now())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
