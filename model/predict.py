import pickle
import numpy as np

_bundle = None


def _load_model():
    global _bundle
    if _bundle is None:
        with open("model/model.pkl", "rb") as f:
            _bundle = pickle.load(f)
    return _bundle


def predict(origin: str, destination: str, carrier: str,
            weight_kg: float, cbm: float = 0.0,
            promised_days: float = 14,
            fuel_price_index: float = 3.5,
            market_rate_index: float = 1200) -> dict:
    """
    Returns:
      predicted_cost           - estimated freight cost in USD
      predicted_delivery_days  - estimated actual delivery days
      on_time_probability      - probability of on-time delivery (0.0 - 1.0)

    cbm is the ingredient-specific cubic meter volume (from cbm_calculator).
    Freight cost is driven by CBM, not just weight.
    """
    bundle = _load_model()
    encoders = bundle["encoders"]

    # Handle unseen labels gracefully
    def safe_encode(encoder, value, fallback="Other"):
        try:
            return encoder.transform([value])[0]
        except Exception:
            try:
                return encoder.transform([fallback])[0]
            except Exception:
                return 0

    origin_enc  = safe_encode(encoders["origin"], origin)
    dest_enc    = safe_encode(encoders["destination"], destination)
    carrier_enc = safe_encode(encoders["carrier"], carrier)

    cbm_value = cbm if cbm > 0 else weight_kg * 0.002

    features = np.array([[
        origin_enc, dest_enc, carrier_enc,
        weight_kg, cbm_value, promised_days,
        fuel_price_index, market_rate_index
    ]])

    # Retrain-safe: try with cbm feature first, fall back to without if model is old
    try:
        predicted_cost = round(float(bundle["cost_model"].predict(features)[0]), 2)
        predicted_days = int(round(bundle["days_model"].predict(features)[0]))
        ontime_proba   = round(float(bundle["ontime_model"].predict_proba(features)[0][1]), 2)
    except Exception:
        # Old model without cbm column — drop cbm and retry
        features_no_cbm = np.array([[
            origin_enc, dest_enc, carrier_enc,
            weight_kg, promised_days,
            fuel_price_index, market_rate_index
        ]])
        predicted_cost = round(float(bundle["cost_model"].predict(features_no_cbm)[0]), 2)
        predicted_days = int(round(bundle["days_model"].predict(features_no_cbm)[0]))
        ontime_proba   = round(float(bundle["ontime_model"].predict_proba(features_no_cbm)[0][1]), 2)

    return {
        "predicted_cost": predicted_cost,
        "predicted_delivery_days": predicted_days,
        "on_time_probability": ontime_proba
    }
