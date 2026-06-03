from __future__ import annotations
import httpx

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"


class SapClient:
    def __init__(self, base_url: str, http: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(base_url=self.base_url, timeout=30)
        self._token: str | None = None

    # ---- internals ----
    def _csrf(self) -> str:
        if self._token is None:
            r = self.http.get(f"{SO}/", headers={"X-CSRF-Token": "Fetch"})
            self._token = r.headers.get("X-CSRF-Token", "FAKE-SAP-CSRF-TOKEN")
        return self._token

    def _post(self, path: str, body: dict) -> dict:
        r = self.http.post(path, json=body, headers={"X-CSRF-Token": self._csrf()})
        return self._handle(r)

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self._handle(self.http.get(path, params=params))

    @staticmethod
    def _handle(r: httpx.Response) -> dict:
        data = r.json()
        if r.status_code >= 400:
            err = data.get("error", {})
            out = {"status": "error",
                   "sap_code": err.get("code", "UNKNOWN"),
                   "message": err.get("message", {}).get("value", "")}
            out.update(err.get("detail", {}))
            return out
        d = data["d"]
        entity = d.get("results", d)
        if isinstance(entity, list):
            return {"status": "success", "results": entity}
        return {"status": "success", **entity}

    # ---- operations ----
    def list_customers(self) -> dict:
        return self._get(f"{SO}/A_Customer")

    def list_materials(self) -> dict:
        return self._get(f"{SO}/A_Material")

    def check_availability(self, material: str) -> dict:
        return self._get(f"{SO}/CheckAvailability", {"Material": material})

    def create_sales_order(self, sold_to, sales_org, dist_channel, division, items,
                           purchase_order_by_customer: str = "") -> dict:
        body = {"SoldToParty": sold_to, "SalesOrganization": sales_org,
                "DistributionChannel": dist_channel, "OrganizationDivision": division,
                "PurchaseOrderByCustomer": purchase_order_by_customer,
                "to_Item": [{"Material": i["material"], "RequestedQuantity": i["quantity"]}
                            for i in items]}
        return self._post(f"{SO}/A_SalesOrder", body)

    def get_sales_order(self, sales_order: str) -> dict:
        return self._get(SO + f"/A_SalesOrder('{sales_order}')")

    def release_credit_block(self, sales_order: str, reason: str) -> dict:
        return self._post(f"{SO}/ReleaseCreditBlock", {"SalesOrder": sales_order, "Reason": reason})

    def apply_pricing_condition(self, sales_order: str, item: str, amount: float) -> dict:
        return self._post(f"{SO}/ApplyPricingCondition",
                          {"SalesOrder": sales_order, "SalesOrderItem": item, "ConditionAmount": amount})

    def create_outbound_delivery(self, sales_order: str, items: list | None = None) -> dict:
        body: dict = {"SalesOrder": sales_order}
        if items:
            body["to_Item"] = [{"SalesOrderItem": i["item"], "ActualDeliveryQuantity": i["quantity"]}
                               for i in items]
        return self._post(f"{DLV}/A_OutbDeliveryHeader", body)

    def post_goods_issue(self, delivery: str) -> dict:
        return self._post(f"{DLV}/PostGoodsIssue", {"OutboundDelivery": delivery})

    def create_billing_document(self, delivery: str) -> dict:
        return self._post(f"{BILL}/A_BillingDocument", {"OutboundDelivery": delivery})

    def get_billing_document(self, billing: str) -> dict:
        return self._get(BILL + f"/A_BillingDocument('{billing}')")

    def get_document_flow(self, sales_order: str) -> dict:
        return self._get(SO + f"/A_SalesOrder('{sales_order}')/to_DocumentFlow")
