"""
Unit tests for CBM calculator.
Run: docker exec ai-module pytest tests/test_cbm.py -v
"""
import pytest
from freight.cbm_calculator import calculate_cbm, recommend_container, estimate


def test_chamomile_cbm():
    result = calculate_cbm("chamomile", 1000)
    assert result["cbm_raw"] == pytest.approx(7.0, rel=0.01)
    assert result["cbm_with_packaging"] == pytest.approx(7.7, rel=0.01)


def test_sugar_cbm():
    result = calculate_cbm("sugar", 1000)
    assert result["cbm_raw"] == pytest.approx(0.70, rel=0.01)


def test_chamomile_takes_more_space_than_sugar():
    chamomile = calculate_cbm("chamomile", 1000)
    sugar = calculate_cbm("sugar", 1000)
    assert chamomile["cbm_raw"] > sugar["cbm_raw"] * 5


def test_unknown_ingredient_uses_default():
    result = calculate_cbm("mystery_spice", 1000)
    from freight.cbm_calculator import DENSITY_FACTORS
    assert result["density_factor"] == DENSITY_FACTORS["default"]


def test_lcl_recommendation():
    # Small order of dense ingredient should be LCL
    result = recommend_container(cbm=5.0, weight_kg=500)
    assert result["recommended_container"] == "LCL"


def test_20fcl_recommendation():
    result = recommend_container(cbm=20.0, weight_kg=1000)
    assert result["recommended_container"] == "20_FCL"


def test_40fcl_recommendation():
    result = recommend_container(cbm=40.0, weight_kg=2000)
    assert result["recommended_container"] == "40_FCL"


def test_estimate_returns_all_fields():
    result = estimate("turmeric", 3000)
    assert "ingredient" in result
    assert "cbm" in result
    assert "container" in result
    assert result["weight_kg"] == 3000
    assert result["cbm"] > 0


def test_zero_weight_cbm():
    result = calculate_cbm("chamomile", 0)
    assert result["cbm_raw"] == 0.0
