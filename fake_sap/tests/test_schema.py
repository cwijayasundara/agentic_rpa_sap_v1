from fake_sap import schema


def test_sales_order_has_key_and_credit_status_field():
    et = schema.A_SALES_ORDER
    assert et.name == "A_SalesOrder"
    keys = [p.name for p in et.properties if p.is_key]
    assert keys == ["SalesOrder"]
    by_name = {p.name: p for p in et.properties}
    assert by_name["TotalCreditCheckStatus"].edm_type == "Edm.String"
    assert by_name["TotalCreditCheckStatus"].max_length == 1
    assert by_name["TotalNetAmount"].edm_type == "Edm.Decimal"


def test_item_has_composite_key():
    keys = [p.name for p in schema.A_SALES_ORDER_ITEM.properties if p.is_key]
    assert keys == ["SalesOrder", "SalesOrderItem"]


def test_services_registry_covers_three_services():
    assert set(schema.SERVICES) == {
        "API_SALES_ORDER_SRV",
        "API_OUTBOUND_DELIVERY_SRV",
        "API_BILLING_DOCUMENT_SRV",
    }
    so = schema.SERVICES["API_SALES_ORDER_SRV"]
    set_names = [name for name, _ in so.entity_sets]
    assert set_names == [
        "A_SalesOrder", "A_SalesOrderItem", "A_SalesOrderScheduleLine",
    ]
