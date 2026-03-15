"""
NetSuite connection tests.
Run: docker exec ai-module pytest tests/test_netsuite.py -v

Note: These tests make real API calls to NetSuite.
They will fail if credentials are missing or network is unavailable.
"""
import pytest
from netsuite.client import run_suiteql


def test_vendor_query_returns_results():
    results = run_suiteql("SELECT id, companyname FROM vendor FETCH FIRST 5 ROWS ONLY")
    assert isinstance(results, list)
    assert len(results) > 0


def test_vendor_has_expected_fields():
    results = run_suiteql("SELECT id, companyname FROM vendor FETCH FIRST 1 ROWS ONLY")
    assert len(results) == 1
    row = results[0]
    assert "id" in row
    assert "companyname" in row


def test_item_query_returns_results():
    results = run_suiteql(
        "SELECT id, itemid, displayname FROM item WHERE isinactive = 'F' FETCH FIRST 5 ROWS ONLY"
    )
    assert isinstance(results, list)
    assert len(results) > 0


def test_invalid_query_raises_exception():
    with pytest.raises(Exception):
        run_suiteql("SELECT * FROM nonexistent_table_xyz")
