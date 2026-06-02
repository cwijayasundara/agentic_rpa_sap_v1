import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"


@pytest.fixture
def client():
    return TestClient(create_app())


def csrf(client):
    r = client.get(f"{SO}/", headers={"X-CSRF-Token": "Fetch"})
    return r.headers["X-CSRF-Token"]


def test_csrf_fetch_returns_token(client):
    r = client.get(f"{SO}/", headers={"X-CSRF-Token": "Fetch"})
    assert r.status_code == 200
    assert r.headers["X-CSRF-Token"] == "FAKE-SAP-CSRF-TOKEN"


def test_create_order_without_csrf_is_403(client):
    r = client.post(f"{SO}/A_SalesOrder", json={
        "SoldToParty": "1000001", "SalesOrganization": "1010",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}],
    })
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"


def test_create_happy_order_prices_correctly(client):
    token = csrf(client)
    r = client.post(f"{SO}/A_SalesOrder",
        headers={"X-CSRF-Token": token},
        json={"SoldToParty": "1000001", "SalesOrganization": "1010",
              "DistributionChannel": "10", "OrganizationDivision": "00",
              "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}]})
    assert r.status_code == 201
    d = r.json()["d"]
    assert d["SalesOrder"] == "4500000000"
    assert d["TotalNetAmount"] == 500.0
    assert d["CreditBlock"] is False
    assert d["PricingStatus"] == "complete"


def test_create_order_for_blocked_customer_sets_credit_block(client):
    token = csrf(client)
    r = client.post(f"{SO}/A_SalesOrder", headers={"X-CSRF-Token": token},
        json={"SoldToParty": "1000002", "SalesOrganization": "1010",
              "DistributionChannel": "10", "OrganizationDivision": "00",
              "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}]})
    assert r.status_code == 201
    assert r.json()["d"]["CreditBlock"] is True


def test_create_order_missing_pricing_is_incomplete_zero(client):
    token = csrf(client)
    r = client.post(f"{SO}/A_SalesOrder", headers={"X-CSRF-Token": token},
        json={"SoldToParty": "1000001", "SalesOrganization": "1010",
              "DistributionChannel": "10", "OrganizationDivision": "00",
              "to_Item": [{"Material": "MZ-FG-NP", "RequestedQuantity": 10}]})
    d = r.json()["d"]
    assert d["TotalNetAmount"] == 0.0
    assert d["PricingStatus"] == "incomplete"


def test_get_unknown_order_is_404(client):
    r = client.get(f"{SO}/A_SalesOrder('9999999999')")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
