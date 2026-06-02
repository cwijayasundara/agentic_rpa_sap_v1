from __future__ import annotations

CSRF_TOKEN = "FAKE-SAP-CSRF-TOKEN"


def odata_single(entity: dict) -> dict:
    return {"d": entity}


def odata_collection(entities: list[dict]) -> dict:
    return {"d": {"results": entities}}


def odata_error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": {"lang": "en", "value": message}}}
