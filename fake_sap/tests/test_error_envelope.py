from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"


def test_error_body_has_innererror_errordetails():
    client = TestClient(create_app())
    r = client.get(SO + "/A_SalesOrder('NOPE')")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["message"]["value"]
    details = err["innererror"]["errordetails"]
    assert details[0]["code"] == "NOT_FOUND"
    assert details[0]["severity"] == "error"
