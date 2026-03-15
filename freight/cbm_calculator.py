"""
CBM (Cubic Meter) Calculator

- Freight cost is based on SPACE (CBM), not just weight
- Different ingredients take up different amounts of space per kg
- Density factors come from Monday.com Product Form, with hardcoded fallbacks
- Add 10% for packaging
- Then decide: LCL, 20ft FCL, or 40ft FCL container
"""

# Density factors by Monday.com Product Form (CBM per kg)
# Volumetric multiplier per ingredient type
PRODUCT_FORM_DENSITY = {
    "liquid":        0.00100,
    "powder":        0.00350,
    "dried":         0.00600,
    "cut":           0.00550,
    "whole":         0.00650,
    "pieces":        0.00500,
    "dried pieces":  0.00550,
    "default":       0.00200,
}

# Fallback density factors — used only when Monday.com is unavailable
# Primary source is PRODUCT_FORM_DENSITY mapped from Monday.com Product Form column
DENSITY_FACTORS = {
    "default": 0.00200,  # ~500 kg/m³ — mid-range estimate for unknown ingredients
}

# Cache of ingredient name → density factor loaded from Monday.com
_monday_density_cache: dict = {}


def load_density_from_monday(board_id: str = "5027158260") -> dict:
    """
    Load density factors from Monday.com ingredient board.
    Maps ingredient name → density factor based on Product Form.
    Called once at startup or on demand.
    """
    global _monday_density_cache
    try:
        import requests, json, os
        from dotenv import load_dotenv
        load_dotenv()

        token = os.getenv("MONDAY_API_KEY")
        if not token:
            return {}

        headers = {"Authorization": token, "Content-Type": "application/json"}
        all_items = []
        cursor = None

        while True:
            if cursor:
                q = json.dumps({"query": f'{{ boards(ids: [{board_id}]) {{ items_page(limit: 100, cursor: "{cursor}") {{ cursor items {{ name column_values {{ column {{ title }} text }} }} }} }} }}'})
            else:
                q = json.dumps({"query": f'{{ boards(ids: [{board_id}]) {{ items_page(limit: 100) {{ cursor items {{ name column_values {{ column {{ title }} text }} }} }} }} }}'})

            r = requests.post("https://api.monday.com/v2", headers=headers, data=q, timeout=10)
            page = r.json()["data"]["boards"][0]["items_page"]
            all_items.extend(page["items"])
            cursor = page.get("cursor")
            if not cursor:
                break

        cache = {}
        for item in all_items:
            cols = {c["column"]["title"]: c["text"] for c in item["column_values"]}
            product_form = cols.get("Product Form", "").strip().lower()
            density = PRODUCT_FORM_DENSITY.get(product_form, PRODUCT_FORM_DENSITY["default"])
            name_key = item["name"].strip().lower().replace(" ", "_").replace("-", "_")
            cache[name_key] = density

        _monday_density_cache = cache
        return cache
    except Exception:
        return {}

# Container specifications
CONTAINERS = {
    "LCL": {
        "max_cbm":  15.0,
        "max_kg":   28000,
        "description": "Less than Container Load (shared container) — charged per CBM"
    },
    "20_FCL": {
        "max_cbm":  28.0,
        "max_kg":   28000,
        "description": "20ft Full Container Load — fixed container price"
    },
    "40_FCL": {
        "max_cbm":  58.0,
        "max_kg":   28000,
        "description": "40ft Full Container Load — fixed container price"
    },
}

PACKAGING_ALLOWANCE = 0.10  # 10% extra for packaging


def get_density_factor(ingredient_name: str) -> float:
    """
    Returns CBM per kg for a given ingredient.
    Priority: Monday.com board → hardcoded fallback → default
    """
    name = ingredient_name.lower().replace(" ", "_").replace("-", "_")
    # 1. Check Monday.com cache (loaded from Product Form)
    if _monday_density_cache and name in _monday_density_cache:
        return _monday_density_cache[name]
    # 2. Hardcoded specific ingredient fallback
    if name in DENSITY_FACTORS:
        return DENSITY_FACTORS[name]
    # 3. Default
    return DENSITY_FACTORS["default"]


def calculate_cbm(ingredient_name: str, weight_kg: float) -> dict:
    """
    Calculate total CBM for a given ingredient and weight.
    Includes 10% packaging allowance.

    Returns:
        dict with cbm, cbm_with_packaging, density_factor
    """
    density = get_density_factor(ingredient_name)
    cbm_raw = weight_kg * density
    cbm_with_packaging = cbm_raw * (1 + PACKAGING_ALLOWANCE)

    return {
        "ingredient":          ingredient_name,
        "weight_kg":           weight_kg,
        "density_factor":      density,
        "cbm_raw":             round(cbm_raw, 4),
        "cbm_with_packaging":  round(cbm_with_packaging, 4),
        "packaging_allowance": f"{int(PACKAGING_ALLOWANCE * 100)}%",
    }


def recommend_container(cbm: float, weight_kg: float) -> dict:
    """
    Recommend the best container type based on CBM and weight.

    Returns:
        dict with recommended container type and reason
    """
    if cbm <= CONTAINERS["LCL"]["max_cbm"] and weight_kg <= CONTAINERS["LCL"]["max_kg"]:
        container = "LCL"
        reason = f"CBM ({cbm:.2f}) is under 15 — shared container is most cost-effective"
    elif cbm <= CONTAINERS["20_FCL"]["max_cbm"] and weight_kg <= CONTAINERS["20_FCL"]["max_kg"]:
        container = "20_FCL"
        reason = f"CBM ({cbm:.2f}) fits in a 20ft container (max 28 CBM)"
    elif cbm <= CONTAINERS["40_FCL"]["max_cbm"] and weight_kg <= CONTAINERS["40_FCL"]["max_kg"]:
        container = "40_FCL"
        reason = f"CBM ({cbm:.2f}) requires a 40ft container (max 58 CBM)"
    else:
        container = "MULTIPLE_40_FCL"
        containers_needed = int(cbm / CONTAINERS["40_FCL"]["max_cbm"]) + 1
        reason = f"CBM ({cbm:.2f}) exceeds one 40ft container — need {containers_needed} containers"

    return {
        "recommended_container": container,
        "description": CONTAINERS.get(container, {}).get("description", "Multiple containers required"),
        "reason": reason,
        "cbm": round(cbm, 4),
        "weight_kg": weight_kg,
    }


def estimate(ingredient_name: str, weight_kg: float) -> dict:
    """
    Full CBM estimate for an ingredient order.
    Returns CBM calculation + container recommendation.

    Example:
        estimate("chamomile", 5000)
        → CBM = 38.5 → recommend 40_FCL
    """
    cbm_data = calculate_cbm(ingredient_name, weight_kg)
    container_data = recommend_container(cbm_data["cbm_with_packaging"], weight_kg)

    return {
        "ingredient":           ingredient_name,
        "weight_kg":            weight_kg,
        "cbm":                  cbm_data["cbm_with_packaging"],
        "container":            container_data["recommended_container"],
        "container_reason":     container_data["reason"],
        "packaging_allowance":  cbm_data["packaging_allowance"],
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
    _logger = logging.getLogger(__name__)

    # Test examples
    test_cases = [
        ("sugar",    10000),
        ("chamomile", 5000),
        ("ginger_juice", 8000),
        ("turmeric",  3000),
    ]

    _logger.info("=== CBM Calculator Test ===")
    for ingredient, weight in test_cases:
        result = estimate(ingredient, weight)
        _logger.info("Ingredient: %s", result["ingredient"])
        _logger.info("  Weight:     %s kg", f"{result['weight_kg']:,}")
        _logger.info("  CBM:        %s m³", result["cbm"])
        _logger.info("  Container:  %s", result["container"])
        _logger.info("  Reason:     %s", result["container_reason"])
