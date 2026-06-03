from __future__ import annotations
from fake_sap.store import SalesOrder, SalesOrderItem, Delivery, BillingDocument, Store

# Simulated, fixed demo timestamps so serialized output is deterministic.
_ORDER_DATE_MS = 1780444800000      # ~2026-06-03 (simulated)
_REQ_DELIV_MS = 1780790400000       # ~2026-06-07 (simulated)
_CURRENCY = "USD"


def _odata_date(ms: int) -> str:
    return f"/Date({ms})/"


def _delivery_status(order: SalesOrder, store: Store) -> str:
    dlvs = [d for d in store.deliveries.values() if d.sales_order == order.sales_order]
    if not dlvs:
        return "A"
    ordered = {it.item: it.quantity for it in order.items}
    delivered: dict[str, int] = {}
    fully_gi = True
    for d in dlvs:
        if d.goods_issue_status != "C":
            fully_gi = False
        for it in d.items:
            delivered[it.item] = delivered.get(it.item, 0) + it.quantity
    complete = fully_gi and all(delivered.get(i, 0) >= q for i, q in ordered.items())
    return "C" if complete else "B"


def _billing_status(order: SalesOrder, store: Store) -> str:
    dlv_ids = {d.delivery for d in store.deliveries.values()
               if d.sales_order == order.sales_order}
    invoiced = any(b.delivery in dlv_ids for b in store.billing_documents.values())
    return "C" if invoiced else "A"


def _overall_status(order: SalesOrder, store: Store, blocked: bool) -> str:
    if blocked:
        return "B"
    d = _delivery_status(order, store)
    b = _billing_status(order, store)
    if d == "C" and b == "C":
        return "C"
    if d == "A" and b == "A":
        return "A"
    return "B"


def _schedule_line_dict(order: SalesOrder, item: SalesOrderItem, store: Store) -> dict:
    mat = store.materials.get(item.material)
    confirmed_qty = min(item.quantity, mat.stock) if mat else 0
    fully_confirmed = confirmed_qty >= item.quantity
    return {
        "SalesOrder": order.sales_order,
        "SalesOrderItem": item.item,
        "ScheduleLine": "0001",
        "RequestedDeliveryDate": _odata_date(_REQ_DELIV_MS),
        "ConfirmedDeliveryDate": _odata_date(_REQ_DELIV_MS) if fully_confirmed else "",
        "ScheduleLineOrderQuantity": item.quantity,
        "ConfdOrderQtyByMatlAvailCheck": confirmed_qty,
        "OrderQuantityUnit": "EA",
    }


def sales_order_item_dict(order: SalesOrder, item: SalesOrderItem, store: Store) -> dict:
    return {
        "SalesOrder": order.sales_order,
        "SalesOrderItem": item.item,
        "Material": item.material,
        "SalesOrderItemCategory": "TAN",
        "RequestedQuantity": item.quantity,
        "RequestedQuantityUnit": "EA",
        "NetAmount": item.net_amount,
        "TransactionCurrency": _CURRENCY,
        # convenience alias (back-compat)
        "PricingIncomplete": item.pricing_incomplete,
        "to_ScheduleLine": [_schedule_line_dict(order, item, store)],
    }


def sales_order_to_dict(order: SalesOrder, store: Store) -> dict:
    blocked = order.credit_block
    return {
        "SalesOrder": order.sales_order,
        "SalesOrderType": "OR",
        "SalesOrganization": order.sales_org,
        "DistributionChannel": order.dist_channel,
        "OrganizationDivision": order.division,
        "SoldToParty": order.sold_to,
        "PurchaseOrderByCustomer": order.purchase_order_by_customer,
        "SalesOrderDate": _odata_date(_ORDER_DATE_MS),
        "CreationDate": _odata_date(_ORDER_DATE_MS),
        "RequestedDeliveryDate": _odata_date(_REQ_DELIV_MS),
        "TransactionCurrency": _CURRENCY,
        "TotalNetAmount": order.total_net_amount,  # numeric for back-compat
        "TotalCreditCheckStatus": "B" if blocked else "A",
        "DeliveryBlockReason": "01" if blocked else "",
        "OverallDeliveryStatus": _delivery_status(order, store),
        "OverallOrdReltdBillgStatus": _billing_status(order, store),
        "OverallSDProcessStatus": _overall_status(order, store, blocked),
        # convenience aliases (back-compat)
        "CreditBlock": order.credit_block,
        "PricingStatus": order.pricing_status,
        "to_Item": [sales_order_item_dict(order, it, store) for it in order.items],
    }


def delivery_to_dict(delivery: Delivery) -> dict:
    gi_done = delivery.goods_issue_status == "C"
    return {
        "OutboundDelivery": delivery.delivery,
        "SalesOrder": delivery.sales_order,
        "GoodsMovementStatus": "C" if gi_done else "A",
        # convenience alias (back-compat)
        "GoodsIssueStatus": delivery.goods_issue_status,
        "to_Item": [
            {"OutboundDelivery": delivery.delivery, "DeliveryDocumentItem": it.item,
             "Material": it.material, "ActualDeliveryQuantity": it.quantity,
             "DeliveryQuantityUnit": "EA"}
            for it in delivery.items
        ],
    }


def billing_to_dict(bill: BillingDocument) -> dict:
    return {
        "BillingDocument": bill.billing_document,
        "OutboundDelivery": bill.delivery,
        "TotalNetAmount": bill.total_net_amount,  # numeric for back-compat
        "TransactionCurrency": _CURRENCY,
    }
