import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"
T = {"X-CSRF-Token": "FAKE-SAP-CSRF-TOKEN"}


@pytest.fixture
def client():
    return TestClient(create_app())


def full_chain_order(client, material="MZ-FG-C100", qty=10):
    so = client.post(f"{SO}/A_SalesOrder", headers=T, json={
        "SoldToParty": "1000001", "SalesOrganization": "1010",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": material, "RequestedQuantity": qty}]}).json()["d"]["SalesOrder"]
    dlv = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so}).json()["d"]["OutboundDelivery"]
    return so, dlv


def test_billing_before_goods_issue_is_doc_flow_error(client):
    so, dlv = full_chain_order(client)
    r = client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "DOC_FLOW"


def test_billing_after_goods_issue_totals_correctly(client):
    so, dlv = full_chain_order(client)
    client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    r = client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    assert r.status_code == 201
    d = r.json()["d"]
    assert d["BillingDocument"] == "9000000000"
    assert d["TotalNetAmount"] == 500.0


def test_missing_pricing_yields_zero_invoice(client):
    so, dlv = full_chain_order(client, material="MZ-FG-NP")
    client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    r = client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    assert r.json()["d"]["TotalNetAmount"] == 0.0


def test_document_flow_lists_delivery_and_billing(client):
    so, dlv = full_chain_order(client)
    client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    r = client.get(SO + f"/A_SalesOrder('{so}')/to_DocumentFlow")
    docs = r.json()["d"]["results"]
    types = {row["DocumentType"] for row in docs}
    assert types == {"SalesOrder", "OutboundDelivery", "BillingDocument"}
