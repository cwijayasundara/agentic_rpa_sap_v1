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
