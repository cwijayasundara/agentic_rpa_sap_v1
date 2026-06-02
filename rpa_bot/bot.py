from __future__ import annotations
from mcp_server.sap_client import SapClient

SCENARIOS = {
    "happy": {"sold_to": "1000001", "material": "MZ-FG-C100", "quantity": 10},
    "credit_hold": {"sold_to": "1000002", "material": "MZ-FG-C100", "quantity": 10},
    "out_of_stock": {"sold_to": "1000001", "material": "MZ-FG-OOS", "quantity": 10},
    "missing_pricing": {"sold_to": "1000001", "material": "MZ-FG-NP", "quantity": 10},
}


def run_rpa(scenario_key: str, client: SapClient) -> dict:
    """Classic RPA: fixed sequence, no recovery. Halts on first error."""
    sc = SCENARIOS[scenario_key]
    steps: list[dict] = []

    def record(name: str, res: dict, detail: str | None = None) -> bool:
        ok = res.get("status") == "success"
        if detail is None:
            detail = res.get("sap_code") if not ok else (
                res.get("SalesOrder") or res.get("OutboundDelivery") or res.get("BillingDocument"))
        steps.append({"step": name, "ok": ok, "detail": detail})
        return ok

    def order_detail(res: dict) -> str | None:
        # Surface the data problems the order was created WITH, so a later
        # delivery/billing failure is self-explanatory in the demo.
        if res.get("status") != "success":
            return None
        detail = res.get("SalesOrder")
        flags = []
        if res.get("CreditBlock"):
            flags.append("CreditBlock=true")
        if res.get("PricingStatus") == "incomplete":
            flags.append("PricingStatus=incomplete")
        return f"{detail}, " + ", ".join(flags) if flags else detail

    order = client.create_sales_order(sc["sold_to"], "1010", "10", "00",
                                      [{"material": sc["material"], "quantity": sc["quantity"]}])
    if not record("create_sales_order", order, order_detail(order)):
        return {"status": "ESCALATED", "failed_step": "create_sales_order",
                "steps": steps, "invoice_total": None}

    dlv = client.create_outbound_delivery(order["SalesOrder"])
    if not record("create_outbound_delivery", dlv):
        return {"status": "ESCALATED", "failed_step": "create_outbound_delivery",
                "steps": steps, "invoice_total": None}

    gi = client.post_goods_issue(dlv["OutboundDelivery"])
    if not record("post_goods_issue", gi):
        return {"status": "ESCALATED", "failed_step": "post_goods_issue",
                "steps": steps, "invoice_total": None}

    bill = client.create_billing_document(dlv["OutboundDelivery"])
    if not record("create_billing_document", bill):
        return {"status": "ESCALATED", "failed_step": "create_billing_document",
                "steps": steps, "invoice_total": None}

    # Classic RPA never validates the amount — reports success even at $0.
    return {"status": "COMPLETED", "failed_step": None,
            "steps": steps, "invoice_total": bill["TotalNetAmount"]}
