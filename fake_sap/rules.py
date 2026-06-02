from __future__ import annotations
from fake_sap.store import Store


class SapError(Exception):
    """Raised for SAP business-rule violations. Carries an OData-style code."""

    def __init__(self, code: str, message: str, http_status: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail or {}


def price_item(store: Store, material: str, quantity: int) -> tuple[float, bool]:
    """Return (net_amount, pricing_incomplete). Missing condition -> 0.0 + incomplete."""
    mat = store.materials.get(material)
    if mat is None:
        raise SapError("NOT_FOUND", f"Material {material} not found", 404)
    if not mat.pricing_condition_exists:
        return 0.0, True
    return round(mat.list_price * quantity, 2), False


def is_credit_blocked(store: Store, sold_to: str) -> bool:
    cust = store.customers.get(sold_to)
    if cust is None:
        raise SapError("NOT_FOUND", f"Customer {sold_to} not found", 404)
    return not cust.credit_ok


def check_atp(store: Store, material: str, quantity: int) -> None:
    mat = store.materials.get(material)
    if mat is None:
        raise SapError("NOT_FOUND", f"Material {material} not found", 404)
    if quantity > mat.stock:
        raise SapError(
            "INSUFFICIENT_STOCK",
            f"Only {mat.stock} units of {material} available (requested {quantity})",
            400,
            {"available": mat.stock, "requested": quantity},
        )
