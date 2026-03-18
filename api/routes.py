import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from freight.cbm_calculator import estimate as cbm_estimate
from netsuite.queries import STOCK_ON_HAND_QUERY, PRICING_MATRIX_QUERY, VENDOR_PAYMENT_TERMS_QUERY

logger = logging.getLogger(__name__)
router = APIRouter()


class FreightRequest(BaseModel):
    ingredient: str
    origin: str
    destination: str
    weight_kg: float
    carrier: str


class FreightResponse(BaseModel):
    ingredient: str
    weight_kg: float
    cbm: float
    container: str
    container_reason: str
    predicted_cost: float
    predicted_delivery_days: int
    on_time_probability: float
    currency: str
    note: Optional[str] = None


# POST /api/estimate
# Calculates CBM from ingredient type + weight, recommends container (LCL/20ft/40ft FCL),
# and predicts freight cost (USD), delivery days, and on-time probability via Random Forest model.
# Example: { "ingredient": "chamomile", "origin": "China", "destination": "Australia",
#            "weight_kg": 5000, "carrier": "Sea Freight" }
@router.post("/estimate", response_model=FreightResponse)
def estimate_freight(request: FreightRequest):
    if request.weight_kg <= 0:
        raise HTTPException(status_code=422, detail="weight_kg must be greater than 0")

    try:
        cbm_data = cbm_estimate(request.ingredient, request.weight_kg)
    except Exception as e:
        logger.error("CBM calculation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"CBM calculation error: {e}")

    note = None

    # Run model prediction
    try:
        from model.predict import predict
        pred = predict(
            origin=request.origin,
            destination=request.destination,
            carrier=request.carrier,
            weight_kg=request.weight_kg,
            cbm=cbm_data["cbm"],  # ingredient-specific CBM is the primary cost driver
        )
        predicted_cost          = pred["predicted_cost"]
        predicted_delivery_days = pred["predicted_delivery_days"]
        on_time_probability     = pred["on_time_probability"]
    except Exception as e:
        logger.warning("Model prediction failed: %s", e)
        predicted_cost          = 0.0
        predicted_delivery_days = 0
        on_time_probability     = 0.0
        note = note or f"Model prediction unavailable: {e}"

    # Save prediction to Supabase for history and model retraining
    try:
        from db.client import get_client
        get_client().table("predictions").insert({
            "ingredient":              request.ingredient,
            "origin":                  request.origin,
            "destination":             request.destination,
            "carrier":                 request.carrier,
            "weight_kg":               request.weight_kg,
            "cbm":                     cbm_data["cbm"],
            "predicted_cost":          predicted_cost,
            "predicted_delivery_days": predicted_delivery_days,
            "on_time_probability":     on_time_probability,
        }).execute()
    except Exception as e:
        logger.warning("Failed to save prediction to Supabase: %s", e)

    return FreightResponse(
        ingredient=request.ingredient,
        weight_kg=request.weight_kg,
        cbm=cbm_data["cbm"],
        container=cbm_data["container"],
        container_reason=cbm_data["container_reason"],
        predicted_cost=predicted_cost,
        predicted_delivery_days=predicted_delivery_days,
        on_time_probability=on_time_probability,
        currency="USD",
        note=note,
    )


# GET /api/stock
# Returns items with positive stock at main warehouse (NetSuite location ID=510).
# Excludes virtual/allocated locations (520, 523, 524).
# Fields: item_id, sku, item_name, location_id, quantityonhand, quantityavailable
@router.get("/stock")
def get_stock_on_hand():
    from netsuite.client import run_suiteql
    try:
        records = run_suiteql(STOCK_ON_HAND_QUERY)
    except Exception as e:
        logger.error("Stock on hand query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"NetSuite error: {e}")
    return records


# GET /api/pricing
# Unit prices per price level for all active items (Base Price, Online Price, etc.).
# Optional filter: ?item_id=123 to return a single item only.
# Fields: item_id, sku, item_name, price_level_id, unit_price
@router.get("/pricing")
def get_pricing_matrix(item_id: Optional[int] = None):
    from netsuite.client import run_suiteql
    try:
        records = run_suiteql(PRICING_MATRIX_QUERY)
    except Exception as e:
        logger.error("Pricing matrix query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"NetSuite error: {e}")
    if item_id is not None:
        records = [r for r in records if str(r.get("item_id")) == str(item_id)]
    return records


# GET /api/vendors/payment-terms
# Vendors from NetSuite that have a payment term set.
# Term IDs: 7=Net30, 8=Net60, 23=Net45, 61=Net90,
#           34=30%Deposit/70%BeforeShipment, 35=50%Deposit/50%BeforeShipment, 55=DueOnReceipt
# Fields: vendor_id, vendor_name, payment_terms_id, currency_id, email, phone
@router.get("/vendors/payment-terms")
def get_vendor_payment_terms():
    from netsuite.client import run_suiteql
    try:
        records = run_suiteql(VENDOR_PAYMENT_TERMS_QUERY)
    except Exception as e:
        logger.error("Vendor payment terms query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"NetSuite error: {e}")
    return records


# GET /api/ingredients?board_id=5027158260
# Full ingredient list from a Monday.com board with all column values
# (Product Form, category, supplier, etc.).
@router.get("/ingredients")
def get_ingredients(board_id: str):
    from monday.client import get_ingredient_list
    try:
        return get_ingredient_list(board_id)
    except Exception as e:
        logger.error("Monday.com ingredient fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/ingredients/search?board_id=5027158260&name=chamomile
# Case-insensitive partial name search against a Monday.com board.
# Returns 404 if no match is found.
@router.get("/ingredients/search")
def search_ingredient(board_id: str, name: str):
    from monday.client import search_ingredient
    try:
        result = search_ingredient(board_id, name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Ingredient '{name}' not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Monday.com ingredient search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/ingredients/boards
# Lists all Monday.com boards the API token has access to.
# Returns id, name, description, state, items_count — use to find board IDs.
@router.get("/ingredients/boards")
def get_monday_boards():
    from monday.client import get_boards
    try:
        return get_boards()
    except Exception as e:
        logger.error("Monday.com boards fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/ingredients/specs?name=chamomile
# Returns spec sheets and COAs for an ingredient from Supabase (synced from Box).
# Partial name match — e.g. "acai" returns "Acai Berry Powder" records.
@router.get("/ingredients/specs")
def get_ingredient_specs(name: str):
    from db.client import get_client
    try:
        db = get_client()
        r = db.table("ingredient_specs").select("*").ilike("ingredient_name", f"%{name}%").execute()
        if not r.data:
            raise HTTPException(status_code=404, detail=f"No specs found for '{name}'")
        return r.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ingredient specs fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/ingredients/origin?sku=ORG-LEM-GRS-1
# Returns all available countries of origin for an ingredient (by SKU).
# If multiple origins exist, the salesperson must select one before building a quote.
# Country is extracted from NetSuite vendor names on Purchase Orders.
@router.get("/ingredients/origin")
def get_ingredient_origin(sku: str):
    from netsuite.client import run_suiteql
    from netsuite.country import extract_country
    from netsuite.queries import INGREDIENT_VENDOR_QUERY
    try:
        query = INGREDIENT_VENDOR_QUERY.format(sku=sku)
        results = run_suiteql(query)
        if not results:
            raise HTTPException(status_code=404, detail=f"No purchase history found for SKU '{sku}'")

        # Collect unique vendor + country combinations
        seen = set()
        origins = []
        item_name = results[0].get("item_name", "")
        for r in results:
            country = extract_country(r.get("vendor_name", ""))
            if not country:
                continue
            key = (r["vendor_id"], country)
            if key not in seen:
                seen.add(key)
                origins.append({
                    "vendor_id":   r["vendor_id"],
                    "vendor_name": r["vendor_name"],
                    "country":     country,
                })

        if not origins:
            raise HTTPException(status_code=404, detail=f"No country of origin found for SKU '{sku}'")

        return {
            "sku":             sku,
            "item_name":       item_name,
            "origins":         origins,
            "requires_selection": len(origins) > 1,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ingredient origin fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# GET /api/status
# Health check — returns service status and whether model.pkl is loaded.
# If model_loaded is false, /estimate returns 0 for cost and on-time probability.
@router.get("/status")
def status():
    import os
    from config import MODEL_PATH
    model_loaded = os.path.exists(MODEL_PATH)
    return {"status": "ready", "model_loaded": model_loaded}
