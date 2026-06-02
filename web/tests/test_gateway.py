import pytest
from starlette.testclient import TestClient
import web.server as web
from fake_sap.app import create_app
from mcp_server.sap_client import SapClient


@pytest.fixture
def client(monkeypatch):
    # Point the gateway's RPA client at an in-process Fake-SAP.
    http = TestClient(create_app(), base_url="http://sap")
    sap = SapClient(base_url="http://sap", http=http)
    monkeypatch.setattr(web, "get_rpa_client", lambda: sap)
    return TestClient(web.app)


def test_rpa_run_happy(client):
    r = client.post("/api/rpa/run", json={"scenario": "happy"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["invoice_total"] == 500.0


def test_rpa_run_credit_hold_escalates(client):
    r = client.post("/api/rpa/run", json={"scenario": "credit_hold"})
    assert r.json()["status"] == "ESCALATED"
