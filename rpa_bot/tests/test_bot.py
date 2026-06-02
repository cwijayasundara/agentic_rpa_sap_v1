import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app
from mcp_server.sap_client import SapClient
from rpa_bot.bot import run_rpa, SCENARIOS


@pytest.fixture
def client():
    http = TestClient(create_app(), base_url="http://sap")
    return SapClient(base_url="http://sap", http=http)


def test_happy_path_completes_with_correct_invoice(client):
    res = run_rpa("happy", client)
    assert res["status"] == "COMPLETED"
    assert res["invoice_total"] == 500.0


def test_credit_hold_escalates_at_delivery(client):
    res = run_rpa("credit_hold", client)
    assert res["status"] == "ESCALATED"
    assert res["failed_step"] == "create_outbound_delivery"


def test_out_of_stock_escalates_at_delivery(client):
    res = run_rpa("out_of_stock", client)
    assert res["status"] == "ESCALATED"
    assert res["failed_step"] == "create_outbound_delivery"


def test_missing_pricing_completes_but_invoice_is_zero(client):
    res = run_rpa("missing_pricing", client)
    assert res["status"] == "COMPLETED"
    assert res["invoice_total"] == 0.0  # silently wrong — the RPA failure mode


def _order_step(res):
    return next(s for s in res["steps"] if s["step"] == "create_sales_order")


def test_credit_hold_order_step_shows_credit_block_cause(client):
    res = run_rpa("credit_hold", client)
    detail = _order_step(res)["detail"]
    assert "4500000000" in detail
    assert "CreditBlock=true" in detail


def test_missing_pricing_order_step_shows_pricing_cause(client):
    res = run_rpa("missing_pricing", client)
    detail = _order_step(res)["detail"]
    assert "PricingStatus=incomplete" in detail


def test_happy_order_step_detail_is_just_the_number(client):
    res = run_rpa("happy", client)
    assert _order_step(res)["detail"] == "4500000000"
