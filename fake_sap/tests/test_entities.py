from fake_sap.store import Store, SalesOrder, SalesOrderItem, Delivery, DeliveryItem, BillingDocument
from fake_sap import entities, schema


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
    store.materials["MZ-FG-C100"] = __import__("fake_sap.store", fromlist=["Material"]).Material(
        "MZ-FG-C100", "Pump", 100, 50.0, True)
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
    store.materials["MZ-FG-C100"] = __import__("fake_sap.store", fromlist=["Material"]).Material(
        "MZ-FG-C100", "Pump", 100, 50.0, True)
    o = _order(store, blocked=True)
    d = entities.sales_order_to_dict(o, store)
    assert d["TotalCreditCheckStatus"] == "B"
    assert d["DeliveryBlockReason"] == "01"
    assert d["OverallSDProcessStatus"] == "B"


def test_order_dict_keys_cover_registry_properties():
    store = Store()
    store.materials["MZ-FG-C100"] = __import__("fake_sap.store", fromlist=["Material"]).Material(
        "MZ-FG-C100", "Pump", 100, 50.0, True)
    d = entities.sales_order_to_dict(_order(store), store)
    for prop in schema.A_SALES_ORDER.properties:
        assert prop.name in d, f"missing authentic field {prop.name}"


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
