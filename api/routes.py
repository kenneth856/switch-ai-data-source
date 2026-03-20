import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from freight.cbm_calculator import estimate as cbm_estimate
from netsuite.queries import STOCK_ON_HAND_QUERY, PRICING_MATRIX_QUERY, VENDOR_PAYMENT_TERMS_QUERY, PURCHASE_COST_QUERY, ITEM_QUERY

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


# GET /api/ingredients
# Master ingredient list from NetSuite — all active items regardless of stock level.
# Optional param: ?sku=CHAM-001 to filter by a specific SKU.
# Fields: item_id, sku, item_name, itemtype, weight, weightunit, purchase_cost
@router.get("/ingredients")
def get_ingredients(sku: Optional[str] = None):
    from netsuite.client import run_suiteql
    try:
        records = run_suiteql(ITEM_QUERY)
    except Exception as e:
        logger.error("Ingredients query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"NetSuite error: {e}")
    if sku:
        records = [r for r in records if r.get("sku") == sku]
    if not records:
        raise HTTPException(status_code=404, detail="No ingredients found")
    return records


# GET /api/stock
# Returns items with positive stock at main warehouse (NetSuite location ID=510).
# Excludes virtual/allocated locations (520, 523, 524).
# Optional params: sku (filter by item SKU), warehouse_id (default 510 = SS Main Warehouse)
# Fields: item_id, sku, item_name, warehouse_id, quantityonhand, quantityavailable
# Supports multiple: ?warehouse_id=510&warehouse_id=215
@router.get("/stock")
def get_stock_on_hand(sku: Optional[str] = None, warehouse_id: List[int] = Query(default=[510, 215])):
    from netsuite.client import run_suiteql
    try:
        sku_filter = f"AND i.itemid = '{sku}'" if sku else ""
        warehouse_ids = ",".join(str(w) for w in warehouse_id)
        query = STOCK_ON_HAND_QUERY.format(warehouse_ids=warehouse_ids, sku_filter=sku_filter)
        records = run_suiteql(query)
    except Exception as e:
        logger.error("Stock on hand query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"NetSuite error: {e}")
    if not records:
        raise HTTPException(status_code=404, detail="No stock found")
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


# GET /api/ingredients/margins?sku=ORG-CHA-PWD-1
# Returns purchase cost and sell prices at 30%, 40%, 50% margin for a given SKU.
# Purchase cost is taken from the most recent Purchase Order line in NetSuite.
# Margin formula: sell_price = purchase_cost / (1 - margin)
@router.get("/ingredients/margins")
def get_ingredient_margins(sku: str):
    from netsuite.client import run_suiteql
    try:
        query = PURCHASE_COST_QUERY.format(sku=sku)
        results = run_suiteql(query)
        if not results:
            raise HTTPException(status_code=404, detail=f"No purchase cost found for SKU '{sku}'")
        r = results[0]
        cost = float(r.get("purchase_cost") or 0)
        if cost <= 0:
            raise HTTPException(status_code=404, detail=f"Purchase cost is zero for SKU '{sku}'")
        return {
            "sku":           r.get("sku"),
            "item_name":     r.get("item_name"),
            "purchase_cost": round(cost, 4),
            "last_po_date":  r.get("last_po_date"),
            "margins": {
                "30%": round(cost / 0.70, 4),
                "40%": round(cost / 0.60, 4),
                "50%": round(cost / 0.50, 4),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ingredient margins fetch failed: %s", e)
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
