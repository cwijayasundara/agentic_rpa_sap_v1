import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
T = {"X-CSRF-Token": "FAKE-SAP-CSRF-TOKEN"}


@pytest.fixture
def client():
    return TestClient(create_app())


def make_order(client, sold_to, material, qty=10):
    r = client.post(f"{SO}/A_SalesOrder", headers=T, json={
        "SoldToParty": sold_to, "SalesOrganization": "1010",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": material, "RequestedQuantity": qty}]})
    return r.json()["d"]["SalesOrder"]


def test_delivery_blocked_by_credit(client):
    so = make_order(client, "1000002", "MZ-FG-C100")
    r = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CREDIT_BLOCK"


def test_delivery_insufficient_stock(client):
    so = make_order(client, "1000001", "MZ-FG-OOS", qty=10)
    r = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so})
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == "INSUFFICIENT_STOCK"
    assert body["detail"]["available"] == 3


def test_partial_delivery_for_available_qty(client):
    so = make_order(client, "1000001", "MZ-FG-OOS", qty=10)
    r = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={
        "SalesOrder": so, "to_Item": [{"SalesOrderItem": "000010", "ActualDeliveryQuantity": 3}]})
    assert r.status_code == 201
    assert r.json()["d"]["OutboundDelivery"] == "8000000000"


def test_post_goods_issue_decrements_stock(client):
    so = make_order(client, "1000001", "MZ-FG-C100", qty=10)
    dlv = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so}).json()["d"]["OutboundDelivery"]
    r = client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    assert r.status_code == 200
    assert r.json()["d"]["GoodsIssueStatus"] == "C"
    assert client.app.state.store.materials["MZ-FG-C100"].stock == 90
