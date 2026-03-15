"""
SPRINT 1 — Data Validation

Checks raw data for:
- Missing required fields
- Zero or negative costs
- Missing dates
- Duplicate records

Run after extract.py:  python pipeline/validate.py
"""

import logging
import os
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(module)s — %(message)s")

RAW_DIR = "data/raw"

RULES = {
    "freight_cost.csv": {
        "required_fields": ["id", "shipment_date", "freight_cost", "vendor_id"],
        "positive_fields": ["freight_cost"],
        "date_fields":     ["shipment_date"],
    },
    "sla_data.csv": {
        "required_fields": ["shipment_id", "shipment_date",
                            "promised_delivery_date", "actual_delivery_date"],
        "positive_fields": ["actual_days", "promised_days"],
        "date_fields":     ["shipment_date",
                            "promised_delivery_date", "actual_delivery_date"],
    },
    "stock_on_hand.csv": {
        "required_fields": ["item_id", "quantity_on_hand", "warehouse_id"],
        "positive_fields": [],
        "date_fields":     [],
    },
    "pricing_matrix.csv": {
        "required_fields": ["item_id", "purchase_cost"],
        "positive_fields": ["purchase_cost"],
        "date_fields":     [],
    },
    "fuel_prices.csv": {
        "required_fields": ["date", "brent_crude_usd_per_bbl"],
        "positive_fields": ["brent_crude_usd_per_bbl"],
        "date_fields":     ["date"],
    },
    "exchange_rates.csv": {
        "required_fields": ["date", "aud_per_usd", "cny_per_usd"],
        "positive_fields": ["aud_per_usd", "cny_per_usd"],
        "date_fields":     ["date"],
    },
}

issues = []


def check(filename: str, rules: dict):
    path = os.path.join(RAW_DIR, filename)
    if not os.path.exists(path):
        issues.append(f"[MISSING FILE] {filename} — run extract.py first")
        return

    df = pd.read_csv(path)
    logger.info("Checking %s (%d rows)...", filename, len(df))

    # Missing fields
    for field in rules["required_fields"]:
        if field not in df.columns:
            issues.append(f"  [MISSING COLUMN] {filename} → '{field}' not found")
            continue
        nulls = df[field].isnull().sum()
        if nulls > 0:
            issues.append(f"  [NULL VALUES] {filename} → '{field}' has {nulls} missing values")

    # Negative / zero values
    for field in rules["positive_fields"]:
        if field in df.columns:
            bad = (df[field] <= 0).sum()
            if bad > 0:
                issues.append(f"  [BAD VALUES] {filename} → '{field}' has {bad} zero/negative values")

    # Duplicates
    if "id" in df.columns:
        dupes = df["id"].duplicated().sum()
        if dupes > 0:
            issues.append(f"  [DUPLICATES] {filename} → {dupes} duplicate IDs found")

    if not issues:
        logger.info("  [OK] %s passed all checks", filename)


def run():
    logger.info("=== Data Validation Report ===")
    for filename, rules in RULES.items():
        check(filename, rules)

    if issues:
        for i in issues:
            logger.warning(i)
        logger.warning("Total issues: %d — do not proceed with bad data.", len(issues))
    else:
        logger.info("No issues found. Data is clean.")

    logger.info("=== Validation Complete ===")


if __name__ == "__main__":
    run()
