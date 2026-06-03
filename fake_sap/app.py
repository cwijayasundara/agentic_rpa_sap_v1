from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from fake_sap.store import (
    Store, SalesOrder, SalesOrderItem, Delivery, DeliveryItem, BillingDocument,
)
from fake_sap.seed import seed_store
from fake_sap import rules, schema
from fake_sap.metadata import render_metadata
from fake_sap.rules import SapError
from fake_sap.odata import odata_single, odata_collection, odata_error_body, CSRF_TOKEN

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"


def _err(e: SapError) -> JSONResponse:
    body = odata_error_body(e.code, e.message)
    if e.detail:
        body["error"]["detail"] = e.detail
    return JSONResponse(body, status_code=e.http_status)


def _require_csrf(request: Request) -> None:
    if request.headers.get("X-CSRF-Token") != CSRF_TOKEN:
        raise SapError("CSRF_FAILED", "CSRF token validation failed", 403)


def _order_to_dict(o: SalesOrder) -> dict:
    return {
        "SalesOrder": o.sales_order,
        "SoldToParty": o.sold_to,
        "SalesOrganization": o.sales_org,
        "DistributionChannel": o.dist_channel,
        "OrganizationDivision": o.division,
        "TotalNetAmount": o.total_net_amount,
        "CreditBlock": o.credit_block,
        "PricingStatus": o.pricing_status,
        "to_Item": [
            {"SalesOrderItem": it.item, "Material": it.material,
             "RequestedQuantity": it.quantity, "NetAmount": it.net_amount,
             "PricingIncomplete": it.pricing_incomplete}
            for it in o.items
        ],
    }


def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="Fake SAP S/4HANA OData")
    if store is None:
        store = Store()
        seed_store(store)
    app.state.store = store

    @app.exception_handler(SapError)
    async def _sap_error_handler(_request: Request, exc: SapError):
        return _err(exc)

    # ---- CSRF fetch (service roots) ----
    @app.get(f"{SO}/")
    @app.get(f"{DLV}/")
    @app.get(f"{BILL}/")
    async def service_root(request: Request):
        headers = {}
        if request.headers.get("X-CSRF-Token", "").lower() == "fetch":
            headers["X-CSRF-Token"] = CSRF_TOKEN
        return JSONResponse({"d": {"EntitySets": []}}, headers=headers)

    @app.get(f"{SO}/$metadata")
    async def so_metadata():
        return Response(render_metadata(schema.SALES_ORDER_SERVICE),
                        media_type="application/xml")

    @app.get(f"{DLV}/$metadata")
    async def dlv_metadata():
        return Response(render_metadata(schema.DELIVERY_SERVICE),
                        media_type="application/xml")

    @app.get(f"{BILL}/$metadata")
    async def bill_metadata():
        return Response(render_metadata(schema.BILLING_SERVICE),
                        media_type="application/xml")

    # ---- master data ----
    @app.get(f"{SO}/A_Customer")
    async def list_customers():
        return odata_collection([
            {"Customer": c.customer, "CustomerName": c.name, "CreditOK": c.credit_ok}
            for c in store.customers.values()
        ])

    @app.get(f"{SO}/A_Material")
    async def list_materials():
        return odata_collection([
            {"Material": m.material, "MaterialName": m.name, "StockQuantity": m.stock,
             "ListPrice": m.list_price, "PricingConditionExists": m.pricing_condition_exists}
            for m in store.materials.values()
        ])

    @app.get(f"{SO}/CheckAvailability")
    async def check_availability(Material: str):
        mat = store.materials.get(Material)
        if mat is None:
            raise SapError("NOT_FOUND", f"Material {Material} not found", 404)
        return odata_single({"Material": Material, "AvailableQuantity": mat.stock})

    @app.post(f"{SO}/Reset")
    async def reset_store():
        seed_store(store)
        return {"d": {"status": "reset"}}

    # ---- sales order ----
    @app.post(f"{SO}/A_SalesOrder", status_code=201)
    async def create_sales_order(request: Request):
        _require_csrf(request)
        payload = await request.json()
        sold_to = payload["SoldToParty"]
        items_in = payload.get("to_Item", [])
        items: list[SalesOrderItem] = []
        pricing_status = "complete"
        for idx, it in enumerate(items_in, start=1):
            net, incomplete = rules.price_item(store, it["Material"], int(it["RequestedQuantity"]))
            if incomplete:
                pricing_status = "incomplete"
            items.append(SalesOrderItem(
                item=f"{idx*10:06d}", material=it["Material"],
                quantity=int(it["RequestedQuantity"]), net_amount=net,
                pricing_incomplete=incomplete))
        order = SalesOrder(
            sales_order=store.next_sales_order(), sold_to=sold_to,
            sales_org=payload["SalesOrganization"], dist_channel=payload["DistributionChannel"],
            division=payload["OrganizationDivision"], items=items,
            credit_block=rules.is_credit_blocked(store, sold_to),
            pricing_status=pricing_status)
        store.sales_orders[order.sales_order] = order
        return odata_single(_order_to_dict(order))

    @app.get(SO + "/A_SalesOrder('{sales_order}')")
    async def get_sales_order(sales_order: str):
        order = store.sales_orders.get(sales_order)
        if order is None:
            raise SapError("NOT_FOUND", f"Sales order {sales_order} not found", 404)
        return odata_single(_order_to_dict(order))

    @app.post(f"{SO}/ReleaseCreditBlock")
    async def release_credit_block(request: Request):
        _require_csrf(request)
        payload = await request.json()
        order = store.sales_orders.get(payload["SalesOrder"])
        if order is None:
            raise SapError("NOT_FOUND", "Sales order not found", 404)
        order.credit_block = False
        return odata_single(_order_to_dict(order))

    @app.post(f"{SO}/ApplyPricingCondition")
    async def apply_pricing_condition(request: Request):
        _require_csrf(request)
        payload = await request.json()
        order = store.sales_orders.get(payload["SalesOrder"])
        if order is None:
            raise SapError("NOT_FOUND", "Sales order not found", 404)
        amount = float(payload["ConditionAmount"])
        item_no = payload["SalesOrderItem"]
        for it in order.items:
            if it.item == item_no:
                it.net_amount = round(amount * it.quantity, 2)
                it.pricing_incomplete = False
        order.pricing_status = "complete" if all(not i.pricing_incomplete for i in order.items) else "incomplete"
        return odata_single(_order_to_dict(order))

    _register_delivery_and_billing(app, store)  # implemented in Task 6 & 7
    return app


def _register_delivery_and_billing(app, store):
    from fastapi import Request
    from fake_sap.store import Delivery, DeliveryItem

    def _delivery_to_dict(d: Delivery) -> dict:
        return {
            "OutboundDelivery": d.delivery,
            "SalesOrder": d.sales_order,
            "GoodsIssueStatus": d.goods_issue_status,
            "to_Item": [{"DeliveryDocumentItem": it.item, "Material": it.material,
                         "ActualDeliveryQuantity": it.quantity} for it in d.items],
        }

    app.state._delivery_to_dict = _delivery_to_dict

    @app.post(f"{DLV}/A_OutbDeliveryHeader", status_code=201)
    async def create_delivery(request: Request):
        _require_csrf(request)
        payload = await request.json()
        order = store.sales_orders.get(payload["SalesOrder"])
        if order is None:
            raise SapError("NOT_FOUND", "Sales order not found", 404)
        if order.credit_block:
            raise SapError("CREDIT_BLOCK", f"Order {order.sales_order} is blocked for credit", 400)
        overrides = {i["SalesOrderItem"]: int(i["ActualDeliveryQuantity"])
                     for i in payload.get("to_Item", [])}
        items: list[DeliveryItem] = []
        for it in order.items:
            qty = overrides.get(it.item, it.quantity)
            rules.check_atp(store, it.material, qty)
            items.append(DeliveryItem(item=it.item, material=it.material, quantity=qty))
        dlv = Delivery(delivery=store.next_delivery(), sales_order=order.sales_order,
                       items=items, goods_issue_status="A")
        store.deliveries[dlv.delivery] = dlv
        return odata_single(_delivery_to_dict(dlv))

    @app.get(DLV + "/A_OutbDeliveryHeader('{delivery}')")
    async def get_delivery(delivery: str):
        d = store.deliveries.get(delivery)
        if d is None:
            raise SapError("NOT_FOUND", f"Delivery {delivery} not found", 404)
        return odata_single(_delivery_to_dict(d))

    @app.post(f"{DLV}/PostGoodsIssue")
    async def post_goods_issue(request: Request):
        _require_csrf(request)
        payload = await request.json()
        d = store.deliveries.get(payload["OutboundDelivery"])
        if d is None:
            raise SapError("NOT_FOUND", "Delivery not found", 404)
        for it in d.items:
            store.materials[it.material].stock -= it.quantity
        d.goods_issue_status = "C"
        return odata_single(_delivery_to_dict(d))

    _register_billing(app, store)  # Task 7


def _register_billing(app, store):
    from fastapi import Request
    from fake_sap.store import BillingDocument

    @app.post(f"{BILL}/A_BillingDocument", status_code=201)
    async def create_billing(request: Request):
        _require_csrf(request)
        payload = await request.json()
        dlv = store.deliveries.get(payload["OutboundDelivery"])
        if dlv is None:
            raise SapError("NOT_FOUND", "Delivery not found", 404)
        if dlv.goods_issue_status != "C":
            raise SapError("DOC_FLOW", "Goods issue must be posted before billing", 400)
        order = store.sales_orders[dlv.sales_order]
        net_by_item = {it.item: (it.net_amount / it.quantity if it.quantity else 0.0)
                       for it in order.items}
        total = round(sum(net_by_item.get(it.item, 0.0) * it.quantity for it in dlv.items), 2)
        bill = BillingDocument(billing_document=store.next_billing(),
                               delivery=dlv.delivery, total_net_amount=total)
        store.billing_documents[bill.billing_document] = bill
        return odata_single({"BillingDocument": bill.billing_document,
                             "OutboundDelivery": bill.delivery,
                             "TotalNetAmount": bill.total_net_amount})

    @app.get(BILL + "/A_BillingDocument('{billing}')")
    async def get_billing(billing: str):
        b = store.billing_documents.get(billing)
        if b is None:
            raise SapError("NOT_FOUND", f"Billing document {billing} not found", 404)
        return odata_single({"BillingDocument": b.billing_document,
                             "OutboundDelivery": b.delivery,
                             "TotalNetAmount": b.total_net_amount})

    @app.get(SO + "/A_SalesOrder('{sales_order}')/to_DocumentFlow")
    async def document_flow(sales_order: str):
        order = store.sales_orders.get(sales_order)
        if order is None:
            raise SapError("NOT_FOUND", "Sales order not found", 404)
        rows = [{"DocumentType": "SalesOrder", "DocumentNumber": order.sales_order,
                 "Status": order.pricing_status}]
        for d in store.deliveries.values():
            if d.sales_order == sales_order:
                rows.append({"DocumentType": "OutboundDelivery", "DocumentNumber": d.delivery,
                             "Status": "GoodsIssued" if d.goods_issue_status == "C" else "Open"})
                for b in store.billing_documents.values():
                    if b.delivery == d.delivery:
                        rows.append({"DocumentType": "BillingDocument",
                                     "DocumentNumber": b.billing_document,
                                     "Status": f"Net {b.total_net_amount}"})
        return odata_collection(rows)
