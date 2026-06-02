import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app
import mcp_server.server as srv
from mcp_server.sap_client import SapClient


@pytest.fixture(autouse=True)
def inject_client():
    http = TestClient(create_app(), base_url="http://sap")
    srv.set_client(SapClient(base_url="http://sap", http=http))
    yield


def test_create_sales_order_tool():
    res = srv.create_sales_order("1000001", "1010", "10", "00",
                                 [{"material": "MZ-FG-C100", "quantity": 10}])
    assert res["status"] == "success"
    assert res["SalesOrder"] == "4500000000"


def test_delivery_credit_block_includes_hint():
    o = srv.create_sales_order("1000002", "1010", "10", "00",
                               [{"material": "MZ-FG-C100", "quantity": 10}])
    res = srv.create_outbound_delivery(o["SalesOrder"])
    assert res["sap_code"] == "CREDIT_BLOCK"
    assert "release_credit_block" in res["hint"]


def test_stock_error_includes_hint_and_available():
    o = srv.create_sales_order("1000001", "1010", "10", "00",
                               [{"material": "MZ-FG-OOS", "quantity": 10}])
    res = srv.create_outbound_delivery(o["SalesOrder"])
    assert res["available"] == 3
    assert "partial" in res["hint"].lower()
