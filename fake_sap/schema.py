from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Property:
    name: str
    edm_type: str  # "Edm.String" | "Edm.Decimal" | "Edm.Boolean" | "Edm.DateTime"
    max_length: int | None = None
    is_key: bool = False


@dataclass(frozen=True)
class EntityType:
    name: str  # OData entity-set name, e.g. "A_SalesOrder"
    properties: tuple[Property, ...]


@dataclass(frozen=True)
class Service:
    namespace: str  # e.g. "API_SALES_ORDER_SRV"
    entity_sets: tuple[tuple[str, "EntityType"], ...]


def _s(name: str, max_length: int | None = None, is_key: bool = False) -> Property:
    return Property(name, "Edm.String", max_length, is_key)


def _dec(name: str) -> Property:
    return Property(name, "Edm.Decimal")


def _dt(name: str) -> Property:
    return Property(name, "Edm.DateTime")


# --- Sales Order service entity types (property names lifted from the spec) ---
A_SALES_ORDER = EntityType("A_SalesOrder", (
    _s("SalesOrder", 10, is_key=True),
    _s("SalesOrderType", 4),
    _s("SalesOrganization", 4),
    _s("DistributionChannel", 2),
    _s("OrganizationDivision", 2),
    _s("SoldToParty", 10),
    _s("PurchaseOrderByCustomer", 35),
    _dt("SalesOrderDate"),
    _dt("CreationDate"),
    _dt("RequestedDeliveryDate"),
    _s("TransactionCurrency", 5),
    _dec("TotalNetAmount"),
    _s("TotalCreditCheckStatus", 1),
    _s("DeliveryBlockReason", 2),
    _s("OverallDeliveryStatus", 1),
    _s("OverallOrdReltdBillgStatus", 1),
    _s("OverallSDProcessStatus", 1),
))

A_SALES_ORDER_ITEM = EntityType("A_SalesOrderItem", (
    _s("SalesOrder", 10, is_key=True),
    _s("SalesOrderItem", 6, is_key=True),
    _s("Material", 40),
    _s("SalesOrderItemCategory", 4),
    _dec("RequestedQuantity"),
    _s("RequestedQuantityUnit", 3),
    _dec("NetAmount"),
    _s("TransactionCurrency", 5),
))

A_SALES_ORDER_SCHEDULE_LINE = EntityType("A_SalesOrderScheduleLine", (
    _s("SalesOrder", 10, is_key=True),
    _s("SalesOrderItem", 6, is_key=True),
    _s("ScheduleLine", 4, is_key=True),
    _dt("RequestedDeliveryDate"),
    _dt("ConfirmedDeliveryDate"),
    _dec("ScheduleLineOrderQuantity"),
    _dec("ConfdOrderQtyByMatlAvailCheck"),
    _s("OrderQuantityUnit", 3),
))

# --- Invented services (hand-declared, same shape) ---
A_OUTB_DELIVERY_HEADER = EntityType("A_OutbDeliveryHeader", (
    _s("OutboundDelivery", 10, is_key=True),
    _s("SalesOrder", 10),
    _s("GoodsMovementStatus", 1),
))

A_OUTB_DELIVERY_ITEM = EntityType("A_OutbDeliveryItem", (
    _s("OutboundDelivery", 10, is_key=True),
    _s("DeliveryDocumentItem", 6, is_key=True),
    _s("Material", 40),
    _dec("ActualDeliveryQuantity"),
    _s("DeliveryQuantityUnit", 3),
))

A_BILLING_DOCUMENT = EntityType("A_BillingDocument", (
    _s("BillingDocument", 10, is_key=True),
    _s("OutboundDelivery", 10),
    _dec("TotalNetAmount"),
    _s("TransactionCurrency", 5),
))

SALES_ORDER_SERVICE = Service("API_SALES_ORDER_SRV", (
    ("A_SalesOrder", A_SALES_ORDER),
    ("A_SalesOrderItem", A_SALES_ORDER_ITEM),
    ("A_SalesOrderScheduleLine", A_SALES_ORDER_SCHEDULE_LINE),
))

DELIVERY_SERVICE = Service("API_OUTBOUND_DELIVERY_SRV", (
    ("A_OutbDeliveryHeader", A_OUTB_DELIVERY_HEADER),
    ("A_OutbDeliveryItem", A_OUTB_DELIVERY_ITEM),
))

BILLING_SERVICE = Service("API_BILLING_DOCUMENT_SRV", (
    ("A_BillingDocument", A_BILLING_DOCUMENT),
))

SERVICES: dict[str, Service] = {
    s.namespace: s for s in (SALES_ORDER_SERVICE, DELIVERY_SERVICE, BILLING_SERVICE)
}
