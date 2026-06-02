from fake_sap.odata import odata_single, odata_collection, odata_error_body, CSRF_TOKEN


def test_single_entity_wrapped_in_d():
    body = odata_single({"SalesOrder": "4500000000"})
    assert body == {"d": {"SalesOrder": "4500000000"}}


def test_collection_wrapped_in_d_results():
    body = odata_collection([{"Material": "X"}])
    assert body == {"d": {"results": [{"Material": "X"}]}}


def test_error_body_shape():
    body = odata_error_body("CREDIT_BLOCK", "blocked")
    assert body == {"error": {"code": "CREDIT_BLOCK", "message": {"lang": "en", "value": "blocked"}}}


def test_csrf_token_is_fixed():
    assert CSRF_TOKEN == "FAKE-SAP-CSRF-TOKEN"
