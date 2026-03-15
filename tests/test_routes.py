"""
API endpoint tests.
Run: docker exec ai-module pytest tests/test_routes.py -v
"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_check():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_status_endpoint():
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "model_loaded" in data


def test_estimate_known_ingredient():
    r = client.post("/api/estimate", json={
        "ingredient": "chamomile",
        "origin": "Shanghai",
        "destination": "Sydney",
        "weight_kg": 5000,
        "carrier": "Maersk",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ingredient"] == "chamomile"
    assert data["cbm"] > 0
    assert data["container"] in ["LCL", "20_FCL", "40_FCL", "MULTIPLE_40_FCL"]


def test_estimate_unknown_ingredient_returns_warning():
    r = client.post("/api/estimate", json={
        "ingredient": "mystery_herb",
        "origin": "Shanghai",
        "destination": "Sydney",
        "weight_kg": 1000,
        "carrier": "DHL",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["note"] is not None
    assert "Unknown ingredient" in data["note"]


def test_estimate_zero_weight_rejected():
    r = client.post("/api/estimate", json={
        "ingredient": "chamomile",
        "origin": "Shanghai",
        "destination": "Sydney",
        "weight_kg": 0,
        "carrier": "DHL",
    })
    assert r.status_code == 422


def test_estimate_missing_field_rejected():
    r = client.post("/api/estimate", json={
        "ingredient": "chamomile",
        "origin": "Shanghai",
        # missing destination, weight_kg, carrier
    })
    assert r.status_code == 422


def test_sla_returns_list():
    r = client.get("/api/sla")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
