"""
External Market Data Scraper
=============================
Pulls publicly available data that affects freight costs.
All sources are free and require no API key.

  1. Brent Crude Oil prices       — Yahoo Finance (BZ=F)
  2. Commodity prices             — Yahoo Finance (NG=F, DX-Y.NYB)
  3. Exchange Rates AUD/USD CNY/USD — open.er-api.com

Output files (data/raw/):
  - fuel_prices.csv
  - commodity_prices.csv
  - exchange_rates.csv

Run manually:   python pipeline/scrape_external.py
Run in Docker:  docker exec ai-module python pipeline/scrape_external.py
"""

import logging
import os
import requests
import pandas as pd
from datetime import datetime, date

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(module)s — %(message)s")

RAW_DIR = "data/raw"
os.makedirs(RAW_DIR, exist_ok=True)

YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}


def save(df: pd.DataFrame, filename: str):
    if df is None or df.empty:
        logger.warning("No data returned for %s", filename)
        return
    path = os.path.join(RAW_DIR, filename)
    df.to_csv(path, index=False)
    logger.info("Saved %d records → %s", len(df), path)


def _fetch_yahoo(symbol: str, label: str, range_: str = "2y", interval: str = "1mo") -> pd.DataFrame:
    """Fetch monthly closing prices from Yahoo Finance for a given symbol."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={interval}&range={range_}"
    )
    resp = requests.get(url, headers=YAHOO_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]

    df = pd.DataFrame({
        "date": pd.to_datetime(timestamps, unit="s").normalize(),
        label: closes,
    })
    return df.dropna().reset_index(drop=True)


# ---------------------------------------------------------------------------
# 1. Brent Crude Oil Prices
#    Symbol: BZ=F (Brent Crude Futures on NY Mercantile)
#    Why: Brent is the global oil benchmark. Carriers apply a Bunker Adjustment
#    Factor (BAF) based on fuel prices — so oil price directly affects freight cost.
# ---------------------------------------------------------------------------
def fetch_fuel_prices() -> pd.DataFrame:
    logger.info("Fetching Brent crude oil prices (Yahoo Finance BZ=F)...")
    try:
        return _fetch_yahoo("BZ=F", "brent_crude_usd_per_bbl")
    except Exception as e:
        logger.error("Fuel price fetch failed: %s", e)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 2. Commodity Prices
#    NG=F     — Natural Gas Futures (USD/MMBtu): energy cost proxy
#    DX-Y.NYB — US Dollar Index: strong USD = more expensive imports for AUD business
# ---------------------------------------------------------------------------
def fetch_commodity_prices() -> pd.DataFrame:
    logger.info("Fetching commodity prices (Yahoo Finance)...")
    symbols = {
        "NG=F":      "natural_gas_usd_per_mmbtu",
        "DX-Y.NYB":  "usd_index",
    }
    frames = []
    for symbol, label in symbols.items():
        try:
            df = _fetch_yahoo(symbol, label)
            frames.append(df)
        except Exception as e:
            logger.warning("%s fetch failed: %s", symbol, e)

    if not frames:
        return pd.DataFrame()

    result = frames[0]
    for df in frames[1:]:
        result = result.merge(df, on="date", how="outer")

    return result.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Exchange Rates: AUD/USD and CNY/USD
#    Source: open.er-api.com (free, no auth required)
#    Why: Switch Supply buys from China (pays CNY), earns in AUD.
#    Currency fluctuation directly affects landed cost and margin.
# ---------------------------------------------------------------------------
def fetch_exchange_rates() -> pd.DataFrame:
    logger.info("Fetching exchange rates AUD/USD, CNY/USD (open.er-api.com)...")
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=15)
        resp.raise_for_status()
        rates = resp.json().get("rates", {})
        if not rates:
            raise ValueError("Empty rates response")

        df = pd.DataFrame([{
            "date": date.today().isoformat(),
            "aud_per_usd": rates.get("AUD"),
            "cny_per_usd": rates.get("CNY"),
        }])
        df["date"] = pd.to_datetime(df["date"])
        return df

    except Exception as e:
        logger.error("Exchange rate fetch failed: %s", e)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    logger.info("=== External Data Scraping Started: %s ===", datetime.now())

    save(fetch_fuel_prices(),      "fuel_prices.csv")
    save(fetch_commodity_prices(), "commodity_prices.csv")
    save(fetch_exchange_rates(),   "exchange_rates.csv")

    logger.info("=== External Data Scraping Complete: %s ===", datetime.now())


if __name__ == "__main__":
    run()
