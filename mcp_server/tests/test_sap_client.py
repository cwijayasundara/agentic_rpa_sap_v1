import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app
from mcp_server.sap_client import SapClient


@pytest.fixture
def sap():
    http = TestClient(create_app(), base_url="http://sap")
    return SapClient(base_url="http://sap", http=http)


def test_create_happy_order(sap):
    res = sap.create_sales_order("1000001", "1010", "10", "00",
                                 [{"material": "MZ-FG-C100", "quantity": 10}])
    assert res["status"] == "success"
    assert res["TotalNetAmount"] == 500.0
    assert res["CreditBlock"] is False


def test_credit_block_surfaces_on_delivery(sap):
    order = sap.create_sales_order("1000002", "1010", "10", "00",
                                   [{"material": "MZ-FG-C100", "quantity": 10}])
    res = sap.create_outbound_delivery(order["SalesOrder"])
    assert res["status"] == "error"
    assert res["sap_code"] == "CREDIT_BLOCK"


def test_insufficient_stock_carries_available(sap):
    order = sap.create_sales_order("1000001", "1010", "10", "00",
                                   [{"material": "MZ-FG-OOS", "quantity": 10}])
    res = sap.create_outbound_delivery(order["SalesOrder"])
    assert res["status"] == "error"
    assert res["sap_code"] == "INSUFFICIENT_STOCK"
    assert res["available"] == 3
