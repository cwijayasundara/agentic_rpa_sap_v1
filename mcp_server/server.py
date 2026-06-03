from __future__ import annotations
import os
from mcp.server.fastmcp import FastMCP
from mcp_server.sap_client import SapClient

mcp = FastMCP("sap-o2c")
_client: SapClient | None = None

HINTS = {
    "CREDIT_BLOCK": "Customer is on credit hold. Call release_credit_block with a business reason, then retry the delivery.",
    "INSUFFICIENT_STOCK": "Not enough stock. Call check_availability, then create a partial outbound delivery for the available quantity and note the backorder.",
    "DOC_FLOW": "A prerequisite document is missing. Ensure goods issue is posted before billing.",
    "NOT_FOUND": "The referenced document does not exist. Re-check the document number.",
}


def set_client(client: SapClient) -> None:
    global _client
    _client = client


def get_client() -> SapClient:
    global _client
    if _client is None:
        _client = SapClient(base_url=os.environ.get("FAKE_SAP_BASE_URL", "http://127.0.0.1:8001"))
    return _client


def _with_hint(res: dict) -> dict:
    if res.get("status") == "error":
        res.setdefault("hint", HINTS.get(res.get("sap_code", ""), "Inspect the error and decide a recovery step."))
    return res


@mcp.tool()
def list_customers() -> dict:
    """List customers with their credit status."""
    return get_client().list_customers()


@mcp.tool()
def list_materials() -> dict:
    """List materials with stock, list price, and whether a pricing condition exists."""
    return get_client().list_materials()


@mcp.tool()
def check_availability(material: str) -> dict:
    """Return the available-to-promise quantity for a material."""
    return get_client().check_availability(material)


@mcp.tool()
def create_sales_order(sold_to: str, sales_org: str, dist_channel: str, division: str,
                       items: list[dict], purchase_order_by_customer: str = "") -> dict:
    """Create a sales order (OData A_SalesOrder).

    items = [{"material": str, "quantity": int}].
    purchase_order_by_customer is the customer's PO reference (optional).
    Returns the header with authentic SAP fields incl. SalesOrderType,
    TransactionCurrency, TotalCreditCheckStatus ("A" ok / "B" blocked),
    DeliveryBlockReason, OverallSDProcessStatus, plus convenience CreditBlock and
    PricingStatus.
    """
    return _with_hint(get_client().create_sales_order(
        sold_to, sales_org, dist_channel, division, items, purchase_order_by_customer))


@mcp.tool()
def get_sales_order(sales_order: str) -> dict:
    """Read a sales order and its items."""
    return _with_hint(get_client().get_sales_order(sales_order))


@mcp.tool()
def release_credit_block(sales_order: str, reason: str) -> dict:
    """Release the credit block on a sales order (simulates credit-management approval)."""
    return _with_hint(get_client().release_credit_block(sales_order, reason))


@mcp.tool()
def apply_pricing_condition(sales_order: str, sales_order_item: str, condition_amount: float) -> dict:
    """Apply a manual unit price to a sales order item to resolve incomplete pricing."""
    return _with_hint(get_client().apply_pricing_condition(sales_order, sales_order_item, condition_amount))


@mcp.tool()
def create_outbound_delivery(sales_order: str, items: list[dict] | None = None) -> dict:
    """Create an outbound delivery. Optional items = [{"item": str, "quantity": int}] for partial delivery."""
    return _with_hint(get_client().create_outbound_delivery(sales_order, items))


@mcp.tool()
def post_goods_issue(delivery: str) -> dict:
    """Post goods issue for a delivery (decrements stock)."""
    return _with_hint(get_client().post_goods_issue(delivery))


@mcp.tool()
def create_billing_document(delivery: str) -> dict:
    """Create a billing document (invoice) from a delivery with posted goods issue."""
    return _with_hint(get_client().create_billing_document(delivery))


@mcp.tool()
def get_billing_document(billing_document: str) -> dict:
    """Read a billing document."""
    return _with_hint(get_client().get_billing_document(billing_document))


@mcp.tool()
def get_document_flow(sales_order: str) -> dict:
    """Return the document flow (order -> delivery -> billing) for a sales order."""
    return _with_hint(get_client().get_document_flow(sales_order))


if __name__ == "__main__":
    mcp.run()
