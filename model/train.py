"""
Run this script once you have real data in data/processed/combined_dataset.csv
Usage: python model/train.py

Expected CSV columns:
  shipment_date, origin, destination, carrier, weight_kg,
  freight_cost, promised_days, actual_days, on_time,
  fuel_price_index, market_rate_index
"""
import logging
import pandas as pd
import pickle
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(module)s — %(message)s")


def train():
    df = pd.read_csv("data/processed/combined_dataset.csv")

    # Encode text columns to numbers
    le_origin   = LabelEncoder()
    le_dest     = LabelEncoder()
    le_carrier  = LabelEncoder()

    df["origin_enc"]      = le_origin.fit_transform(df["origin"])
    df["destination_enc"] = le_dest.fit_transform(df["destination"])
    df["carrier_enc"]     = le_carrier.fit_transform(df["carrier"])

    # Calculate CBM from weight using default density
    # Real CBM per ingredient comes from cbm_calculator at prediction time
    from freight.cbm_calculator import get_density_factor, PACKAGING_ALLOWANCE
    df["cbm"] = df.apply(
        lambda row: row["weight_kg"] * get_density_factor("default") * (1 + PACKAGING_ALLOWANCE),
        axis=1
    )

    features = [
        "origin_enc", "destination_enc", "carrier_enc",
        "weight_kg", "cbm", "promised_days",
        "fuel_price_index", "market_rate_index"
    ]

    X = df[features]

    # --- Model 1: Predict freight COST ---
    y_cost = df["freight_cost"]
    X_train, X_test, y_train, y_test = train_test_split(X, y_cost, test_size=0.2, random_state=42)
    cost_model = RandomForestRegressor(n_estimators=100, random_state=42)
    cost_model.fit(X_train, y_train)
    logger.info("Freight cost model accuracy (R2): %.2f%%", cost_model.score(X_test, y_test) * 100)

    # --- Model 2: Predict DELIVERY DAYS ---
    y_days = df["actual_days"]
    X_train, X_test, y_train, y_test = train_test_split(X, y_days, test_size=0.2, random_state=42)
    days_model = RandomForestRegressor(n_estimators=100, random_state=42)
    days_model.fit(X_train, y_train)
    logger.info("Delivery days model accuracy (R2): %.2f%%", days_model.score(X_test, y_test) * 100)

    # --- Model 3: Predict ON-TIME probability ---
    y_ontime = df["on_time"]  # 1 = on time, 0 = late
    X_train, X_test, y_train, y_test = train_test_split(X, y_ontime, test_size=0.2, random_state=42)
    ontime_model = RandomForestClassifier(n_estimators=100, random_state=42)
    ontime_model.fit(X_train, y_train)
    logger.info("On-time model accuracy: %.2f%%", ontime_model.score(X_test, y_test) * 100)

    # Save all models + encoders together
    with open("model/model.pkl", "wb") as f:
        pickle.dump({
            "cost_model":   cost_model,
            "days_model":   days_model,
            "ontime_model": ontime_model,
            "encoders": {
                "origin":      le_origin,
                "destination": le_dest,
                "carrier":     le_carrier
            }
        }, f)

    logger.info("All models saved to model/model.pkl")


if __name__ == "__main__":
    train()
