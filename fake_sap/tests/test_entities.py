from fake_sap.store import Store, SalesOrder, SalesOrderItem, Delivery, DeliveryItem, BillingDocument, Material
from fake_sap import entities, schema
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"


def _order(store, blocked=False, pricing="complete"):
    o = SalesOrder(
        sales_order="4500000000", sold_to="1000001", sales_org="1710",
        dist_channel="10", division="00",
        items=[SalesOrderItem(item="000010", material="MZ-FG-C100",
                              quantity=10, net_amount=500.0, pricing_incomplete=False)],
        credit_block=blocked, pricing_status=pricing,
        purchase_order_by_customer="PO-4711")
    store.sales_orders[o.sales_order] = o
    return o


def test_order_dict_has_authentic_fields_and_aliases():
    store = Store()
    store.materials["MZ-FG-C100"] = Material("MZ-FG-C100", "Pump", 100, 50.0, True)
    o = _order(store)
    d = entities.sales_order_to_dict(o, store)
    # authentic SAP fields
    assert d["SalesOrderType"] == "OR"
    assert d["TransactionCurrency"] == "USD"
    assert d["TotalCreditCheckStatus"] == "A"
    assert d["DeliveryBlockReason"] == ""
    assert d["PurchaseOrderByCustomer"] == "PO-4711"
    assert d["SalesOrderDate"].startswith("/Date(")
    # monetary stays numeric for back-compat
    assert d["TotalNetAmount"] == 500.0
    # convenience aliases preserved
    assert d["CreditBlock"] is False
    assert d["PricingStatus"] == "complete"
    # item + schedule line fidelity
    it = d["to_Item"][0]
    assert it["RequestedQuantityUnit"] == "EA"
    assert it["SalesOrderItemCategory"] == "TAN"
    sl = it["to_ScheduleLine"][0]
    assert sl["ConfdOrderQtyByMatlAvailCheck"] == 10  # 100 in stock >= 10


def test_credit_block_sets_real_status_fields():
    store = Store()
    store.materials["MZ-FG-C100"] = Material("MZ-FG-C100", "Pump", 100, 50.0, True)
    o = _order(store, blocked=True)
    d = entities.sales_order_to_dict(o, store)
    assert d["TotalCreditCheckStatus"] == "B"
    assert d["DeliveryBlockReason"] == "01"
    assert d["OverallSDProcessStatus"] == "B"


def test_order_dict_keys_cover_registry_properties():
    store = Store()
    store.materials["MZ-FG-C100"] = Material("MZ-FG-C100", "Pump", 100, 50.0, True)
    d = entities.sales_order_to_dict(_order(store), store)
    for prop in schema.A_SALES_ORDER.properties:
        assert prop.name in d, f"missing authentic field {prop.name}"
    item = d["to_Item"][0]
    for prop in schema.A_SALES_ORDER_ITEM.properties:
        assert prop.name in item, f"missing authentic item field {prop.name}"
    sl = item["to_ScheduleLine"][0]
    for prop in schema.A_SALES_ORDER_SCHEDULE_LINE.properties:
        assert prop.name in sl, f"missing authentic schedule-line field {prop.name}"


def test_delivery_and_billing_dicts():
    dlv = Delivery(delivery="8000000000", sales_order="4500000000",
                   items=[DeliveryItem(item="000010", material="MZ-FG-C100", quantity=10)],
                   goods_issue_status="C")
    dd = entities.delivery_to_dict(dlv)
    assert dd["GoodsMovementStatus"] == "C"
    assert dd["GoodsIssueStatus"] == "C"  # alias kept
    assert dd["to_Item"][0]["DeliveryQuantityUnit"] == "EA"
    bill = BillingDocument(billing_document="9000000000", delivery="8000000000",
                           total_net_amount=500.0)
    bd = entities.billing_to_dict(bill)
    assert bd["TransactionCurrency"] == "USD"
    assert bd["TotalNetAmount"] == 500.0


def _csrf(client):
    return client.get(f"{SO}/", headers={"X-CSRF-Token": "Fetch"}).headers["X-CSRF-Token"]


def test_status_codes_progress_through_lifecycle():
    client = TestClient(create_app())
    t = _csrf(client)
    H = {"X-CSRF-Token": t}
    so = client.post(f"{SO}/A_SalesOrder", headers=H, json={
        "SoldToParty": "1000001", "SalesOrganization": "1710",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}]}).json()["d"]
    assert so["OverallDeliveryStatus"] == "A"
    assert so["OverallOrdReltdBillgStatus"] == "A"
    sales_order = so["SalesOrder"]

    dlv = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=H,
                      json={"SalesOrder": sales_order}).json()["d"]["OutboundDelivery"]
    after_dlv = client.get(SO + f"/A_SalesOrder('{sales_order}')").json()["d"]
    assert after_dlv["OverallDeliveryStatus"] == "B"  # delivery exists, GI not posted

    client.post(f"{DLV}/PostGoodsIssue", headers=H, json={"OutboundDelivery": dlv})
    client.post(f"{BILL}/A_BillingDocument", headers=H, json={"OutboundDelivery": dlv})
    final = client.get(SO + f"/A_SalesOrder('{sales_order}')").json()["d"]
    assert final["OverallDeliveryStatus"] == "C"
    assert final["OverallOrdReltdBillgStatus"] == "C"
    assert final["OverallSDProcessStatus"] == "C"
