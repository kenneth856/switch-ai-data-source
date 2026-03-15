"""
Pipeline: Combine raw data into training dataset
=================================================
Merges NetSuite SLA data with vendor, item, and external market data
to produce data/processed/combined_dataset.csv

This is the file that model/train.py reads to train the AI model.

Run manually:   python -m pipeline.combine
Run in Docker:  docker exec ai-module python -m pipeline.combine

Expected input files (data/raw/):
  - sla_data.csv         ← from NetSuite (PurchOrd with shipdate + duedate)
  - vendors.csv          ← from NetSuite
  - transaction_lines.csv ← from NetSuite (for weight/item lookup)
  - items.csv            ← from NetSuite (for weight data)
  - fuel_prices.csv      ← from scrape_external.py
  - exchange_rates.csv   ← from scrape_external.py
"""

import os
import re
import logging
import pandas as pd
from datetime import datetime
from config import DATA_RAW_DIR, DATA_PROCESSED_DIR

logger = logging.getLogger(__name__)
os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)


def extract_origin(vendor_name: str) -> str:
    """Extract country of origin from vendor name (e.g. 'Agrizo - India - 0002' → 'India')."""
    if not isinstance(vendor_name, str):
        return "Unknown"
    # Common country keywords in vendor names
    countries = [
        "Australia", "China", "India", "USA", "Germany", "Italy",
        "Spain", "France", "UK", "Thailand", "Vietnam", "Indonesia",
        "Malaysia", "Japan", "Korea", "Brazil", "Argentina", "Peru",
        "Chile", "Mexico", "Turkey", "Morocco", "Egypt", "South Africa",
        "New Zealand", "Canada", "Netherlands", "Belgium", "Poland",
    ]
    name_upper = vendor_name.upper()
    for c in countries:
        if c.upper() in name_upper:
            return c
    return "Other"


def run():
    logger.info("=== Combine Pipeline Started: %s ===", datetime.now())

    sla_path     = os.path.join(DATA_RAW_DIR, "sla_data.csv")
    vendors_path = os.path.join(DATA_RAW_DIR, "vendors.csv")
    items_path   = os.path.join(DATA_RAW_DIR, "items.csv")
    lines_path   = os.path.join(DATA_RAW_DIR, "transaction_lines.csv")
    fuel_path    = os.path.join(DATA_RAW_DIR, "fuel_prices.csv")
    fx_path      = os.path.join(DATA_RAW_DIR, "exchange_rates.csv")

    if not os.path.exists(sla_path):
        logger.warning("sla_data.csv not found — skipping combine.")
        return

    # --- Load SLA base data ---
    df = pd.read_csv(sla_path)
    df = df.drop(columns=["links"], errors="ignore")
    df["shipment_date"]          = pd.to_datetime(df["shipment_date"],          dayfirst=True, errors="coerce")
    df["promised_delivery_date"] = pd.to_datetime(df["promised_delivery_date"], dayfirst=True, errors="coerce")
    df["actual_delivery_date"]   = pd.to_datetime(df["actual_delivery_date"],   dayfirst=True, errors="coerce")

    # Compute delivery day features
    df["promised_days"] = (df["promised_delivery_date"] - df["shipment_date"]).dt.days
    df["actual_days"]   = (df["actual_delivery_date"]   - df["shipment_date"]).dt.days
    df["on_time"]       = (df["actual_days"] <= df["promised_days"]).astype(int)

    # Rename freight_cost to positive value
    df["freight_cost"] = df["freight_cost"].abs()

    logger.info("  Loaded %d SLA records", len(df))

    # --- Join vendor name → extract origin ---
    if os.path.exists(vendors_path):
        vendors = pd.read_csv(vendors_path)[["vendor_id", "vendor_name"]]
        df = df.merge(vendors, on="vendor_id", how="left")
        df["origin"] = df["vendor_name"].apply(extract_origin)
        logger.info("  Merged vendor/origin data")
    else:
        df["origin"] = "Unknown"

    # Destination is always Australia (Switch Supply is AU-based importer)
    df["destination"] = "Australia"

    # Carrier: derive from origin (placeholder until carrier field is available in NetSuite)
    carrier_map = {
        "China":     "Sea Freight",
        "India":     "Sea Freight",
        "Australia": "Domestic",
        "USA":       "Air Freight",
        "Germany":   "Air Freight",
    }
    df["carrier"] = df["origin"].map(carrier_map).fillna("Sea Freight")

    # --- Join item weight via transaction lines ---
    if os.path.exists(lines_path) and os.path.exists(items_path):
        lines = pd.read_csv(lines_path).drop(columns=["links"], errors="ignore")
        items = pd.read_csv(items_path)[["item_id", "weight", "weightunit"]].drop(columns=["links"], errors="ignore")
        # transaction lines don't have item column in this extract — use freight_cost as weight proxy
        # weight_kg: estimate from freight cost (rough proxy until item join is available)
        logger.warning("  item join not available in transaction lines — estimating weight from cost")

    # Weight estimate: freight cost / avg rate per kg (rough proxy)
    # Will be replaced once item-level data is available from NetSuite
    df["weight_kg"] = (df["freight_cost"] / 3.5).round(1)  # ~$3.50/kg average sea freight rate

    # --- Merge fuel prices (monthly) ---
    df["year_month"] = df["shipment_date"].dt.to_period("M")
    if os.path.exists(fuel_path):
        fuel = pd.read_csv(fuel_path)
        fuel["date"]       = pd.to_datetime(fuel["date"])
        fuel["year_month"] = fuel["date"].dt.to_period("M")
        fuel = fuel[["year_month", "brent_crude_usd_per_bbl"]].rename(
            columns={"brent_crude_usd_per_bbl": "fuel_price_index"}
        )
        df = df.merge(fuel, on="year_month", how="left")
        logger.info("  Merged fuel prices")
    else:
        df["fuel_price_index"] = None

    # market_rate_index: use commodity prices as proxy
    commodity_path = os.path.join(DATA_RAW_DIR, "commodity_prices.csv")
    if os.path.exists(commodity_path):
        comm = pd.read_csv(commodity_path)
        comm["date"]       = pd.to_datetime(comm["date"])
        comm["year_month"] = comm["date"].dt.to_period("M")
        # Use average close price across all commodities as market index
        # Use USD index as market rate proxy
        price_col = "usd_index" if "usd_index" in comm.columns else comm.select_dtypes("number").columns[0]
        comm_monthly = comm.groupby("year_month")[price_col].mean().reset_index()
        comm_monthly = comm_monthly.rename(columns={price_col: "market_rate_index"})
        df = df.merge(comm_monthly, on="year_month", how="left")
        logger.info("  Merged commodity/market rate index")
    else:
        df["market_rate_index"] = None

    # --- Merge exchange rates ---
    if os.path.exists(fx_path):
        fx = pd.read_csv(fx_path)
        df["aud_per_usd"] = fx["aud_per_usd"].iloc[-1]
        df["cny_per_usd"] = fx["cny_per_usd"].iloc[-1]
        logger.info("  Merged exchange rates")
    else:
        df["aud_per_usd"] = None
        df["cny_per_usd"] = None

    # --- Final column selection ---
    df = df.drop(columns=["year_month", "links"], errors="ignore")

    out_path = os.path.join(DATA_PROCESSED_DIR, "combined_dataset.csv")
    df.to_csv(out_path, index=False)
    logger.info("  Saved %d rows → %s", len(df), out_path)
    logger.info("  Columns: %s", list(df.columns))
    logger.info("=== Combine Pipeline Complete: %s ===", datetime.now())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
