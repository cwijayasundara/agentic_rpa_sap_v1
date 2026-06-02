from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Customer:
    customer: str
    name: str
    credit_ok: bool


@dataclass
class Material:
    material: str
    name: str
    stock: int
    list_price: float
    pricing_condition_exists: bool


@dataclass
class SalesOrderItem:
    item: str
    material: str
    quantity: int
    net_amount: float
    pricing_incomplete: bool


@dataclass
class SalesOrder:
    sales_order: str
    sold_to: str
    sales_org: str
    dist_channel: str
    division: str
    items: list[SalesOrderItem]
    credit_block: bool
    pricing_status: str  # "complete" | "incomplete"

    @property
    def total_net_amount(self) -> float:
        return round(sum(i.net_amount for i in self.items), 2)


@dataclass
class DeliveryItem:
    item: str
    material: str
    quantity: int


@dataclass
class Delivery:
    delivery: str
    sales_order: str
    items: list[DeliveryItem]
    goods_issue_status: str  # "A" not posted | "C" posted


@dataclass
class BillingDocument:
    billing_document: str
    delivery: str
    total_net_amount: float


@dataclass
class Store:
    customers: dict[str, Customer] = field(default_factory=dict)
    materials: dict[str, Material] = field(default_factory=dict)
    sales_orders: dict[str, SalesOrder] = field(default_factory=dict)
    deliveries: dict[str, Delivery] = field(default_factory=dict)
    billing_documents: dict[str, BillingDocument] = field(default_factory=dict)
    _so_counter: int = 4500000000
    _dlv_counter: int = 8000000000
    _bill_counter: int = 9000000000

    def next_sales_order(self) -> str:
        n = self._so_counter
        self._so_counter += 1
        return str(n)

    def next_delivery(self) -> str:
        n = self._dlv_counter
        self._dlv_counter += 1
        return str(n)

    def next_billing(self) -> str:
        n = self._bill_counter
        self._bill_counter += 1
        return str(n)
