# SAP O2C RPA-Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable demo proving a multi-agent system replaces classic RPA for SAP Order-to-Cash, by running a brittle scripted RPA bot and a Google-ADK agentic system against the same simulated SAP backend, side-by-side.

**Architecture:** A standalone FastAPI "Fake-SAP" OData service is the shared system-of-record. The RPA bot calls it directly over HTTP; the ADK agents call it through a Python FastMCP tool layer. A FastAPI web app shows both running the same scenario in two panes. Agents recover from exceptions (credit block, short stock, missing pricing) where the RPA bot halts or silently produces wrong results.

**Tech Stack:** Python 3.11+, FastAPI + Starlette TestClient, httpx, `mcp`/FastMCP, `google-adk` (gemini-3.5-flash via Google AI Studio key), pytest, vanilla HTML/JS frontend.

---

## Conventions used throughout this plan

- All commands run from the repo root `/Users/chamindawijayasundara/Documents/rpa_research/sap_rpa_v1`.
- Tests use `pytest`. Run a single test with `uv run pytest <path>::<name> -v` (or `python -m pytest ...` if not using uv).
- **httpx test fixture caveat:** httpx 0.28's `ASGITransport` is async-only, so the in-process test fixtures in Tasks 8–10 and 15 must use `starlette.testclient.TestClient(create_app(), base_url="http://sap")` (a sync `httpx.Client` subclass) instead of `httpx.Client(transport=httpx.ASGITransport(app=...))`. `SapClient` accepts this injected client unchanged.
- We follow the **reference repo's plain ADK package layout** (`agents/o2c_agent/{agent.py,prompts.py,__init__.py}`, runnable via `adk web` / `adk api_server`) rather than `agents-cli scaffold`, to keep this POC self-contained. This is a deliberate, approved deviation from the ADK scaffold prerequisite.
- **Model:** `gemini-3.5-flash`, read from `GEMINI_MODEL`. If the API returns 404 for that ID, fall back to `gemini-flash-latest` (note in README).

### Shared domain fixtures (single source of truth — referenced by many tasks)

Master data seeded deterministically:

| Customer | Name | credit_ok |
|---|---|---|
| `1000001` | Acme Manufacturing | True |
| `1000002` | Globex Industrial | False (credit hold) |

| Material | Name | stock | list_price | pricing_condition_exists |
|---|---|---|---|---|
| `MZ-FG-C100` | Pump C100 | 100 | 50.0 | True |
| `MZ-FG-OOS` | Valve OOS | 3 | 30.0 | True |
| `MZ-FG-NP` | Gasket NP | 100 | 25.0 | **False** |

Number ranges (counters): sales order from `4500000000`, delivery from `8000000000`, billing from `9000000000`.

The four canonical scenarios (all `quantity=10`, `sales_org=1010`, `dist_channel=10`, `division=00`):

| key | sold_to | material | RPA outcome | agent recovery |
|---|---|---|---|---|
| `happy` | 1000001 | MZ-FG-C100 | full chain ok | full chain ok |
| `credit_hold` | 1000002 | MZ-FG-C100 | delivery blocked → halt | `release_credit_block` then proceed |
| `out_of_stock` | 1000001 | MZ-FG-OOS | delivery ATP fail → halt | partial delivery of available 3, note backorder |
| `missing_pricing` | 1000001 | MZ-FG-NP | completes with **$0 invoice** (silently wrong) | `apply_pricing_condition` (25.0) then correct invoice |

### SAP error codes (used by Fake-SAP and mapped by MCP tools)

| sap_code | HTTP | meaning |
|---|---|---|
| `CREDIT_BLOCK` | 400 | delivery blocked by credit hold |
| `INSUFFICIENT_STOCK` | 400 | requested qty > available (payload carries `available`) |
| `DOC_FLOW` | 400 | prerequisite document missing (e.g. billing before goods issue) |
| `NOT_FOUND` | 404 | entity not found |
| `CSRF_FAILED` | 403 | write attempted without valid CSRF token |

---

## Task 1: Project skeleton & dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `fake_sap/__init__.py`, `mcp_server/__init__.py`, `rpa_bot/__init__.py`, `web/__init__.py`, `agents/__init__.py`, `agents/o2c_agent/__init__.py`
- Create: `conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "sap-o2c-rpa-replacement"
version = "0.1.0"
description = "Demo: replacing SAP O2C RPA with a multi-agent system"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "pydantic>=2.7",
    "python-dotenv>=1.0",
    "mcp>=1.2",
    "google-adk>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["fake_sap", "mcp_server", "rpa_bot", "agents", "web"]

[tool.setuptools.packages.find]
where = ["."]
include = ["fake_sap*", "mcp_server*", "rpa_bot*", "web*", "agents*"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Google AI Studio API key for gemini-3.5-flash
GEMINI_API_KEY=your-ai-studio-key-here
GOOGLE_API_KEY=your-ai-studio-key-here
# ADK uses AI Studio (not Vertex) when this is FALSE
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GEMINI_MODEL=gemini-3.5-flash
# Base URL of the Fake-SAP service
FAKE_SAP_BASE_URL=http://127.0.0.1:8001
```

- [ ] **Step 3: Create empty package files**

Create each `__init__.py` listed above as an empty file.

- [ ] **Step 4: Create root `conftest.py`** (makes packages importable in tests)

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 5: Install and verify**

Run: `uv venv && uv pip install -e ".[dev]"` (or `python -m venv .venv && .venv/bin/pip install -e ".[dev]"`)
Expected: installs without error.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example conftest.py fake_sap mcp_server rpa_bot web agents
git commit -m "chore: project skeleton and dependencies"
```

---

## Task 2: Fake-SAP domain store & seed data

**Files:**
- Create: `fake_sap/store.py`
- Create: `fake_sap/seed.py`
- Test: `fake_sap/tests/test_store.py`

- [ ] **Step 1: Write the failing test** (`fake_sap/tests/test_store.py`)

```python
from fake_sap.store import Store
from fake_sap.seed import seed_store


def test_seed_loads_master_data():
    store = Store()
    seed_store(store)
    assert store.customers["1000002"].credit_ok is False
    assert store.materials["MZ-FG-OOS"].stock == 3
    assert store.materials["MZ-FG-NP"].pricing_condition_exists is False


def test_number_ranges_are_deterministic():
    store = Store()
    seed_store(store)
    assert store.next_sales_order() == "4500000000"
    assert store.next_sales_order() == "4500000001"
    assert store.next_delivery() == "8000000000"
    assert store.next_billing() == "9000000000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fake_sap.store'`

- [ ] **Step 3: Implement `fake_sap/store.py`**

```python
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
```

- [ ] **Step 4: Implement `fake_sap/seed.py`**

```python
from fake_sap.store import Store, Customer, Material


def seed_store(store: Store) -> None:
    store.customers.clear()
    store.materials.clear()
    store.sales_orders.clear()
    store.deliveries.clear()
    store.billing_documents.clear()
    store._so_counter = 4500000000
    store._dlv_counter = 8000000000
    store._bill_counter = 9000000000

    for c in [
        Customer("1000001", "Acme Manufacturing", True),
        Customer("1000002", "Globex Industrial", False),
    ]:
        store.customers[c.customer] = c

    for m in [
        Material("MZ-FG-C100", "Pump C100", 100, 50.0, True),
        Material("MZ-FG-OOS", "Valve OOS", 3, 30.0, True),
        Material("MZ-FG-NP", "Gasket NP", 100, 25.0, False),
    ]:
        store.materials[m.material] = m
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_store.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add fake_sap/store.py fake_sap/seed.py fake_sap/tests/test_store.py
git commit -m "feat(fake-sap): domain store and deterministic seed"
```

---

## Task 3: Fake-SAP business rules

**Files:**
- Create: `fake_sap/rules.py`
- Test: `fake_sap/tests/test_rules.py`

- [ ] **Step 1: Write the failing test** (`fake_sap/tests/test_rules.py`)

```python
import pytest
from fake_sap.store import Store
from fake_sap.seed import seed_store
from fake_sap import rules
from fake_sap.rules import SapError


@pytest.fixture
def store():
    s = Store()
    seed_store(s)
    return s


def test_price_item_with_condition(store):
    net, incomplete = rules.price_item(store, "MZ-FG-C100", 10)
    assert net == 500.0
    assert incomplete is False


def test_price_item_missing_condition_is_zero_and_incomplete(store):
    net, incomplete = rules.price_item(store, "MZ-FG-NP", 10)
    assert net == 0.0
    assert incomplete is True


def test_credit_block_flag(store):
    assert rules.is_credit_blocked(store, "1000002") is True
    assert rules.is_credit_blocked(store, "1000001") is False


def test_atp_insufficient_raises_with_available(store):
    with pytest.raises(SapError) as exc:
        rules.check_atp(store, "MZ-FG-OOS", 10)
    assert exc.value.code == "INSUFFICIENT_STOCK"
    assert exc.value.detail["available"] == 3


def test_atp_ok(store):
    rules.check_atp(store, "MZ-FG-C100", 10)  # no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fake_sap.rules'`

- [ ] **Step 3: Implement `fake_sap/rules.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_rules.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add fake_sap/rules.py fake_sap/tests/test_rules.py
git commit -m "feat(fake-sap): credit, ATP and pricing business rules"
```

---

## Task 4: OData envelope & CSRF helpers

**Files:**
- Create: `fake_sap/odata.py`
- Test: `fake_sap/tests/test_odata.py`

- [ ] **Step 1: Write the failing test** (`fake_sap/tests/test_odata.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_odata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fake_sap.odata'`

- [ ] **Step 3: Implement `fake_sap/odata.py`**

```python
from __future__ import annotations

CSRF_TOKEN = "FAKE-SAP-CSRF-TOKEN"


def odata_single(entity: dict) -> dict:
    return {"d": entity}


def odata_collection(entities: list[dict]) -> dict:
    return {"d": {"results": entities}}


def odata_error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": {"lang": "en", "value": message}}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_odata.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add fake_sap/odata.py fake_sap/tests/test_odata.py
git commit -m "feat(fake-sap): OData v2 envelope and CSRF helpers"
```

---

## Task 5: Fake-SAP service — sales order endpoints, CSRF, error handling

**Files:**
- Create: `fake_sap/app.py`
- Test: `fake_sap/tests/test_app_sales_order.py`

The app exposes (OData v2 paths):
- `GET  /sap/opu/odata/sap/API_SALES_ORDER_SRV/` — CSRF fetch (returns `X-CSRF-Token` header when request header `X-CSRF-Token: Fetch`)
- `POST /sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder` — create order (requires valid CSRF token)
- `GET  /sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder('{id}')` — read order (+ items)
- `GET  /sap/opu/odata/sap/API_SALES_ORDER_SRV/A_Customer` and `/A_Material` — master data lists
- `POST .../ReleaseCreditBlock` — clear credit block on an order
- `POST .../ApplyPricingCondition` — set a manual price on an order item
- `GET  .../CheckAvailability?Material='{m}'` — ATP available qty

All write endpoints (`POST`) require header `X-CSRF-Token: FAKE-SAP-CSRF-TOKEN` or return 403 `CSRF_FAILED`.

- [ ] **Step 1: Write the failing test** (`fake_sap/tests/test_app_sales_order.py`)

```python
import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"


@pytest.fixture
def client():
    return TestClient(create_app())


def csrf(client):
    r = client.get(f"{SO}/", headers={"X-CSRF-Token": "Fetch"})
    return r.headers["X-CSRF-Token"]


def test_csrf_fetch_returns_token(client):
    r = client.get(f"{SO}/", headers={"X-CSRF-Token": "Fetch"})
    assert r.status_code == 200
    assert r.headers["X-CSRF-Token"] == "FAKE-SAP-CSRF-TOKEN"


def test_create_order_without_csrf_is_403(client):
    r = client.post(f"{SO}/A_SalesOrder", json={
        "SoldToParty": "1000001", "SalesOrganization": "1010",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}],
    })
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"


def test_create_happy_order_prices_correctly(client):
    token = csrf(client)
    r = client.post(f"{SO}/A_SalesOrder",
        headers={"X-CSRF-Token": token},
        json={"SoldToParty": "1000001", "SalesOrganization": "1010",
              "DistributionChannel": "10", "OrganizationDivision": "00",
              "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}]})
    assert r.status_code == 201
    d = r.json()["d"]
    assert d["SalesOrder"] == "4500000000"
    assert d["TotalNetAmount"] == 500.0
    assert d["CreditBlock"] is False
    assert d["PricingStatus"] == "complete"


def test_create_order_for_blocked_customer_sets_credit_block(client):
    token = csrf(client)
    r = client.post(f"{SO}/A_SalesOrder", headers={"X-CSRF-Token": token},
        json={"SoldToParty": "1000002", "SalesOrganization": "1010",
              "DistributionChannel": "10", "OrganizationDivision": "00",
              "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}]})
    assert r.status_code == 201
    assert r.json()["d"]["CreditBlock"] is True


def test_create_order_missing_pricing_is_incomplete_zero(client):
    token = csrf(client)
    r = client.post(f"{SO}/A_SalesOrder", headers={"X-CSRF-Token": token},
        json={"SoldToParty": "1000001", "SalesOrganization": "1010",
              "DistributionChannel": "10", "OrganizationDivision": "00",
              "to_Item": [{"Material": "MZ-FG-NP", "RequestedQuantity": 10}]})
    d = r.json()["d"]
    assert d["TotalNetAmount"] == 0.0
    assert d["PricingStatus"] == "incomplete"


def test_get_unknown_order_is_404(client):
    r = client.get(f"{SO}/A_SalesOrder('9999999999')")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_app_sales_order.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fake_sap.app'`

- [ ] **Step 3: Implement `fake_sap/app.py`**

```python
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fake_sap.store import (
    Store, SalesOrder, SalesOrderItem, Delivery, DeliveryItem, BillingDocument,
)
from fake_sap.seed import seed_store
from fake_sap import rules
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
```

> Note: `_register_delivery_and_billing` is added in Task 6. For now, define a temporary stub at the bottom of the module so Task 5 imports cleanly:
> ```python
> def _register_delivery_and_billing(app, store):  # replaced in Task 6
>     pass
> ```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_app_sales_order.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add fake_sap/app.py fake_sap/tests/test_app_sales_order.py
git commit -m "feat(fake-sap): sales order endpoints with CSRF and pricing"
```

---

## Task 6: Fake-SAP delivery & goods issue endpoints

**Files:**
- Modify: `fake_sap/app.py` (replace the `_register_delivery_and_billing` stub)
- Test: `fake_sap/tests/test_app_delivery.py`

Endpoints:
- `POST {DLV}/A_OutbDeliveryHeader` — create delivery from an order. Validates credit block (→ `CREDIT_BLOCK`) and ATP per item (→ `INSUFFICIENT_STOCK`). Accepts optional per-item `ActualDeliveryQuantity` for partial delivery.
- `GET  {DLV}/A_OutbDeliveryHeader('{id}')`
- `POST {DLV}/PostGoodsIssue` — set goods_issue_status="C", decrement stock.

- [ ] **Step 1: Write the failing test** (`fake_sap/tests/test_app_delivery.py`)

```python
import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
T = {"X-CSRF-Token": "FAKE-SAP-CSRF-TOKEN"}


@pytest.fixture
def client():
    return TestClient(create_app())


def make_order(client, sold_to, material, qty=10):
    r = client.post(f"{SO}/A_SalesOrder", headers=T, json={
        "SoldToParty": sold_to, "SalesOrganization": "1010",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": material, "RequestedQuantity": qty}]})
    return r.json()["d"]["SalesOrder"]


def test_delivery_blocked_by_credit(client):
    so = make_order(client, "1000002", "MZ-FG-C100")
    r = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CREDIT_BLOCK"


def test_delivery_insufficient_stock(client):
    so = make_order(client, "1000001", "MZ-FG-OOS", qty=10)
    r = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so})
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == "INSUFFICIENT_STOCK"
    assert body["detail"]["available"] == 3


def test_partial_delivery_for_available_qty(client):
    so = make_order(client, "1000001", "MZ-FG-OOS", qty=10)
    r = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={
        "SalesOrder": so, "to_Item": [{"SalesOrderItem": "000010", "ActualDeliveryQuantity": 3}]})
    assert r.status_code == 201
    assert r.json()["d"]["OutboundDelivery"] == "8000000000"


def test_post_goods_issue_decrements_stock(client):
    so = make_order(client, "1000001", "MZ-FG-C100", qty=10)
    dlv = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so}).json()["d"]["OutboundDelivery"]
    r = client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    assert r.status_code == 200
    assert r.json()["d"]["GoodsIssueStatus"] == "C"
    assert client.app.state.store.materials["MZ-FG-C100"].stock == 90
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_app_delivery.py -v`
Expected: FAIL — endpoints return 404 / no such route (stub does nothing).

- [ ] **Step 3: Replace the `_register_delivery_and_billing` stub in `fake_sap/app.py`**

Delete the temporary stub and add this function (it will be fully completed in Task 7; here it registers delivery routes and a billing placeholder):

```python
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


def _register_billing(app, store):  # replaced in Task 7
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_app_delivery.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add fake_sap/app.py fake_sap/tests/test_app_delivery.py
git commit -m "feat(fake-sap): delivery, ATP enforcement and goods issue"
```

---

## Task 7: Fake-SAP billing & document flow endpoints

**Files:**
- Modify: `fake_sap/app.py` (replace the `_register_billing` stub)
- Test: `fake_sap/tests/test_app_billing.py`

Endpoints:
- `POST {BILL}/A_BillingDocument` — create invoice from a delivery. Requires goods issue posted (else `DOC_FLOW`). Total = sum of priced order net amounts for delivered items.
- `GET  {BILL}/A_BillingDocument('{id}')`
- `GET  {SO}/A_SalesOrder('{id}')/to_DocumentFlow` — list related delivery + billing docs.

- [ ] **Step 1: Write the failing test** (`fake_sap/tests/test_app_billing.py`)

```python
import pytest
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"
T = {"X-CSRF-Token": "FAKE-SAP-CSRF-TOKEN"}


@pytest.fixture
def client():
    return TestClient(create_app())


def full_chain_order(client, material="MZ-FG-C100", qty=10):
    so = client.post(f"{SO}/A_SalesOrder", headers=T, json={
        "SoldToParty": "1000001", "SalesOrganization": "1010",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": material, "RequestedQuantity": qty}]}).json()["d"]["SalesOrder"]
    dlv = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=T, json={"SalesOrder": so}).json()["d"]["OutboundDelivery"]
    return so, dlv


def test_billing_before_goods_issue_is_doc_flow_error(client):
    so, dlv = full_chain_order(client)
    r = client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "DOC_FLOW"


def test_billing_after_goods_issue_totals_correctly(client):
    so, dlv = full_chain_order(client)
    client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    r = client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    assert r.status_code == 201
    d = r.json()["d"]
    assert d["BillingDocument"] == "9000000000"
    assert d["TotalNetAmount"] == 500.0


def test_missing_pricing_yields_zero_invoice(client):
    so, dlv = full_chain_order(client, material="MZ-FG-NP")
    client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    r = client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    assert r.json()["d"]["TotalNetAmount"] == 0.0


def test_document_flow_lists_delivery_and_billing(client):
    so, dlv = full_chain_order(client)
    client.post(f"{DLV}/PostGoodsIssue", headers=T, json={"OutboundDelivery": dlv})
    client.post(f"{BILL}/A_BillingDocument", headers=T, json={"OutboundDelivery": dlv})
    r = client.get(SO + f"/A_SalesOrder('{so}')/to_DocumentFlow")
    docs = r.json()["d"]["results"]
    types = {row["DocumentType"] for row in docs}
    assert types == {"SalesOrder", "OutboundDelivery", "BillingDocument"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_app_billing.py -v`
Expected: FAIL — billing route absent (stub).

- [ ] **Step 3: Replace the `_register_billing` stub in `fake_sap/app.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_app_billing.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the whole Fake-SAP suite**

Run: `uv run pytest fake_sap -v`
Expected: PASS (all tests from Tasks 2–7)

- [ ] **Step 6: Commit**

```bash
git add fake_sap/app.py fake_sap/tests/test_app_billing.py
git commit -m "feat(fake-sap): billing, document flow; complete O2C chain"
```

---

## Task 8: SAP OData client for the MCP layer

**Files:**
- Create: `mcp_server/sap_client.py`
- Test: `mcp_server/tests/test_sap_client.py`

`SapClient` wraps httpx, performs the CSRF fetch on first write, and maps OData error envelopes into a structured dict the agent can branch on: `{"status": "error", "sap_code": ..., "message": ..., "available": ...}`. Success returns `{"status": "success", ...entity fields...}`.

The client accepts an injected `httpx.Client` so tests can target the Fake-SAP ASGI app directly.

- [ ] **Step 1: Write the failing test** (`mcp_server/tests/test_sap_client.py`)

```python
import httpx
import pytest
from fake_sap.app import create_app
from mcp_server.sap_client import SapClient


@pytest.fixture
def sap():
    transport = httpx.ASGITransport(app=create_app())
    http = httpx.Client(transport=transport, base_url="http://sap")
    return SapClient(base_url="http://sap", http=http)


def test_create_happy_order(sap):
    res = sap.create_sales_order("1000001", "1010", "10", "00",
                                 [{"material": "MZ-FG-C100", "quantity": 10}])
    assert res["status"] == "success"
    assert res["TotalNetAmount"] == 500.0
    assert res["CreditBlock"] is False


def test_credit_block_surfaces_on_delivery(sap):
    order = sap.create_sales_order("1000002", "1010", "10", "00",
                                   [{"material": "MZ-FG-C100", "quantity": 10}])
    res = sap.create_outbound_delivery(order["SalesOrder"])
    assert res["status"] == "error"
    assert res["sap_code"] == "CREDIT_BLOCK"


def test_insufficient_stock_carries_available(sap):
    order = sap.create_sales_order("1000001", "1010", "10", "00",
                                   [{"material": "MZ-FG-OOS", "quantity": 10}])
    res = sap.create_outbound_delivery(order["SalesOrder"])
    assert res["status"] == "error"
    assert res["sap_code"] == "INSUFFICIENT_STOCK"
    assert res["available"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest mcp_server/tests/test_sap_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.sap_client'`

- [ ] **Step 3: Implement `mcp_server/sap_client.py`**

```python
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

    def create_sales_order(self, sold_to, sales_org, dist_channel, division, items) -> dict:
        body = {"SoldToParty": sold_to, "SalesOrganization": sales_org,
                "DistributionChannel": dist_channel, "OrganizationDivision": division,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest mcp_server/tests/test_sap_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/sap_client.py mcp_server/tests/test_sap_client.py
git commit -m "feat(mcp): SAP OData client with CSRF and structured error mapping"
```

---

## Task 9: FastMCP server exposing O2C tools

**Files:**
- Create: `mcp_server/server.py`
- Test: `mcp_server/tests/test_tools.py`

The tools are thin wrappers over `SapClient`, decorated with FastMCP `@mcp.tool()`. To keep them unit-testable without spawning a process, the tool *functions* are defined at module level and registered with the MCP server; tests import and call the plain functions with an injected client via `set_client()`.

Each error result includes a `hint` to steer agent recovery.

- [ ] **Step 1: Write the failing test** (`mcp_server/tests/test_tools.py`)

```python
import httpx
import pytest
from fake_sap.app import create_app
import mcp_server.server as srv
from mcp_server.sap_client import SapClient


@pytest.fixture(autouse=True)
def inject_client():
    transport = httpx.ASGITransport(app=create_app())
    http = httpx.Client(transport=transport, base_url="http://sap")
    srv.set_client(SapClient(base_url="http://sap", http=http))
    yield


def test_create_sales_order_tool():
    res = srv.create_sales_order("1000001", "1010", "10", "00",
                                 [{"material": "MZ-FG-C100", "quantity": 10}])
    assert res["status"] == "success"
    assert res["SalesOrder"] == "4500000000"


def test_delivery_credit_block_includes_hint():
    o = srv.create_sales_order("1000002", "1010", "10", "00",
                               [{"material": "MZ-FG-C100", "quantity": 10}])
    res = srv.create_outbound_delivery(o["SalesOrder"])
    assert res["sap_code"] == "CREDIT_BLOCK"
    assert "release_credit_block" in res["hint"]


def test_stock_error_includes_hint_and_available():
    o = srv.create_sales_order("1000001", "1010", "10", "00",
                               [{"material": "MZ-FG-OOS", "quantity": 10}])
    res = srv.create_outbound_delivery(o["SalesOrder"])
    assert res["available"] == 3
    assert "partial" in res["hint"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest mcp_server/tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.server'`

- [ ] **Step 3: Implement `mcp_server/server.py`**

```python
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
def create_sales_order(sold_to: str, sales_org: str, dist_channel: str, division: str, items: list[dict]) -> dict:
    """Create a sales order. items = [{"material": str, "quantity": int}]. Returns header incl. CreditBlock and PricingStatus."""
    return _with_hint(get_client().create_sales_order(sold_to, sales_org, dist_channel, division, items))


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
```

> Note on FastMCP `@mcp.tool()`: the decorator registers the tool but the underlying function remains directly callable, so the tests above call e.g. `srv.create_sales_order(...)` synchronously. If the installed `mcp` version wraps the function such that it is not directly callable, change the tests to call `srv.create_sales_order.fn(...)` — verify by running the test in Step 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest mcp_server/tests/test_tools.py -v`
Expected: PASS (3 tests). If failing due to decorator wrapping, apply the `.fn(...)` note above and re-run.

- [ ] **Step 5: Verify the server starts (stdio)**

Run: `FAKE_SAP_BASE_URL=http://127.0.0.1:8001 timeout 3 uv run python -m mcp_server.server` (it should start and wait on stdio; timeout exits cleanly)
Expected: no import errors before timeout.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/server.py mcp_server/tests/test_tools.py
git commit -m "feat(mcp): FastMCP server exposing O2C tools with recovery hints"
```

---

## Task 10: Brittle RPA bot

**Files:**
- Create: `rpa_bot/bot.py`
- Test: `rpa_bot/tests/test_bot.py`

The bot mirrors classic RPA: a fixed step sequence with hard-coded mappings, no recovery. It uses `SapClient` directly (it does NOT use MCP). On any tool error it records the step as failed and **stops** (`status="ESCALATED"`). It does not inspect prices, so a $0 invoice is reported as `COMPLETED` (silently wrong) — exactly the failure we want to contrast.

`run_rpa(scenario_key, client)` returns `{"status": ..., "steps": [...], "invoice_total": float|None}`.

- [ ] **Step 1: Write the failing test** (`rpa_bot/tests/test_bot.py`)

```python
import httpx
import pytest
from fake_sap.app import create_app
from mcp_server.sap_client import SapClient
from rpa_bot.bot import run_rpa, SCENARIOS


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=create_app())
    return SapClient(base_url="http://sap", http=httpx.Client(transport=transport, base_url="http://sap"))


def test_happy_path_completes_with_correct_invoice(client):
    res = run_rpa("happy", client)
    assert res["status"] == "COMPLETED"
    assert res["invoice_total"] == 500.0


def test_credit_hold_escalates_at_delivery(client):
    res = run_rpa("credit_hold", client)
    assert res["status"] == "ESCALATED"
    assert res["failed_step"] == "create_outbound_delivery"


def test_out_of_stock_escalates_at_delivery(client):
    res = run_rpa("out_of_stock", client)
    assert res["status"] == "ESCALATED"
    assert res["failed_step"] == "create_outbound_delivery"


def test_missing_pricing_completes_but_invoice_is_zero(client):
    res = run_rpa("missing_pricing", client)
    assert res["status"] == "COMPLETED"
    assert res["invoice_total"] == 0.0  # silently wrong — the RPA failure mode
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest rpa_bot/tests/test_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rpa_bot.bot'`

- [ ] **Step 3: Implement `rpa_bot/bot.py`**

```python
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

    def record(name: str, res: dict) -> bool:
        ok = res.get("status") == "success"
        steps.append({"step": name, "ok": ok,
                      "detail": res.get("sap_code") if not ok else res.get("SalesOrder")
                      or res.get("OutboundDelivery") or res.get("BillingDocument")})
        return ok

    order = client.create_sales_order(sc["sold_to"], "1010", "10", "00",
                                      [{"material": sc["material"], "quantity": sc["quantity"]}])
    if not record("create_sales_order", order):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest rpa_bot/tests/test_bot.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add rpa_bot/bot.py rpa_bot/tests/test_bot.py
git commit -m "feat(rpa): brittle scripted RPA bot with no recovery"
```

---

## Task 11: ADK agent prompts

**Files:**
- Create: `agents/o2c_agent/prompts.py`

- [ ] **Step 1: Create `agents/o2c_agent/prompts.py`**

```python
SUPERVISOR_INSTRUCTION = """\
You are the O2C Supervisor for a SAP Order-to-Cash process. Given a scenario, you
drive the full chain: create sales order -> outbound delivery -> post goods issue ->
create billing document -> confirm via document flow.

Delegate write/orchestration work to the `creator` sub-agent. Use the `reviewer`
sub-agent to read state and produce the final document-flow summary.

Always finish by asking the reviewer to summarize the document flow, then report to
the user whether the order-to-cash chain completed and the final invoice amount.
"""

CREATOR_INSTRUCTION = """\
You are the O2C Creator. You execute write operations against SAP via tools and you
RECOVER from business exceptions instead of giving up. Standard sequence:

1. create_sales_order(sold_to, sales_org, dist_channel, division, items)
   - If the returned PricingStatus is "incomplete": the item has no pricing condition.
     Call list_materials to find the ListPrice for that material, then
     apply_pricing_condition(sales_order, sales_order_item, condition_amount=ListPrice).
2. create_outbound_delivery(sales_order)
   - If error sap_code == "CREDIT_BLOCK": call release_credit_block(sales_order, reason),
     then retry create_outbound_delivery.
   - If error sap_code == "INSUFFICIENT_STOCK": call check_availability(material),
     then create_outbound_delivery(sales_order, items=[{"item": "<SalesOrderItem>",
     "quantity": <available>}]) for a PARTIAL delivery, and note the backorder.
3. post_goods_issue(delivery)
4. create_billing_document(delivery)

Report each action and any recovery you performed. Never report success on a $0 invoice
without first resolving pricing.
"""

REVIEWER_INSTRUCTION = """\
You are the O2C Reviewer. You only read. Use get_sales_order, get_billing_document and
get_document_flow to verify the final state and produce a concise summary: order number,
delivery number, billing number, final net amount, and any backorder or recovery noted.
"""
```

- [ ] **Step 2: Commit**

```bash
git add agents/o2c_agent/prompts.py
git commit -m "feat(agents): O2C supervisor/creator/reviewer prompts"
```

---

## Task 12: ADK multi-agent system

**Files:**
- Create: `agents/o2c_agent/agent.py`
- Modify: `agents/o2c_agent/__init__.py`
- Test: `agents/o2c_agent/tests/test_agent_build.py`

The Creator and Reviewer each get an `McpToolset` pointed at our stdio MCP server, with `tool_filter` enforcing read/write isolation (Reviewer gets only read tools). The Supervisor delegates via `sub_agents`. Model comes from `GEMINI_MODEL`.

> ADK requires the MCP server path to be absolute. We resolve the repo root at import time and launch `python -m mcp_server.server`.

- [ ] **Step 1: Write the failing test** (`agents/o2c_agent/tests/test_agent_build.py`)

This test only verifies the agent graph builds (no LLM call), so it runs offline.

```python
from agents.o2c_agent.agent import root_agent


def test_root_agent_has_creator_and_reviewer():
    names = {a.name for a in root_agent.sub_agents}
    assert names == {"creator", "reviewer"}


def test_root_agent_model_is_configured():
    assert root_agent.model  # non-empty string
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest agents/o2c_agent/tests/test_agent_build.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.o2c_agent.agent'`

- [ ] **Step 3: Implement `agents/o2c_agent/agent.py`**

```python
from __future__ import annotations
import os
import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from agents.o2c_agent import prompts

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
REPO_ROOT = str(Path(__file__).resolve().parents[2])

READ_TOOLS = ["list_customers", "list_materials", "check_availability",
              "get_sales_order", "get_billing_document", "get_document_flow"]
WRITE_TOOLS = READ_TOOLS + ["create_sales_order", "release_credit_block",
                            "apply_pricing_condition", "create_outbound_delivery",
                            "post_goods_issue", "create_billing_document"]


def _toolset(tool_filter: list[str]) -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "mcp_server.server"],
                cwd=REPO_ROOT,
                env={**os.environ},
            ),
        ),
        tool_filter=tool_filter,
    )


def create_creator() -> Agent:
    return Agent(name="creator", model=MODEL,
                 instruction=prompts.CREATOR_INSTRUCTION, tools=[_toolset(WRITE_TOOLS)])


def create_reviewer() -> Agent:
    return Agent(name="reviewer", model=MODEL,
                 instruction=prompts.REVIEWER_INSTRUCTION, tools=[_toolset(READ_TOOLS)])


root_agent = Agent(
    name="o2c_supervisor",
    model=MODEL,
    instruction=prompts.SUPERVISOR_INSTRUCTION,
    sub_agents=[create_creator(), create_reviewer()],
)
```

- [ ] **Step 4: Update `agents/o2c_agent/__init__.py`**

```python
from agents.o2c_agent.agent import root_agent

__all__ = ["root_agent"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest agents/o2c_agent/tests/test_agent_build.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add agents/o2c_agent/agent.py agents/o2c_agent/__init__.py agents/o2c_agent/tests/test_agent_build.py
git commit -m "feat(agents): supervisor + creator/reviewer with MCP toolsets"
```

---

## Task 13: Live end-to-end agent run (manual + scripted smoke)

**Files:**
- Create: `agents/o2c_agent/run_scenario.py`

This is a runnable script (not a unit test — it calls the real LLM) that starts the Fake-SAP in-process is NOT possible across the MCP subprocess, so it expects Fake-SAP already running on `FAKE_SAP_BASE_URL`. It runs one scenario through the agent via the ADK `Runner` and prints the transcript.

- [ ] **Step 1: Implement `agents/o2c_agent/run_scenario.py`**

```python
from __future__ import annotations
import asyncio
import sys

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.o2c_agent.agent import root_agent

load_dotenv()

PROMPTS = {
    "happy": "Run the full O2C chain for customer 1000001, material MZ-FG-C100, quantity 10 (sales org 1010, channel 10, division 00).",
    "credit_hold": "Run the full O2C chain for customer 1000002, material MZ-FG-C100, quantity 10 (sales org 1010, channel 10, division 00).",
    "out_of_stock": "Run the full O2C chain for customer 1000001, material MZ-FG-OOS, quantity 10 (sales org 1010, channel 10, division 00).",
    "missing_pricing": "Run the full O2C chain for customer 1000001, material MZ-FG-NP, quantity 10 (sales org 1010, channel 10, division 00).",
}


async def main(scenario: str) -> None:
    session_service = InMemorySessionService()
    await session_service.create_session(app_name="o2c", user_id="demo", session_id="s1")
    runner = Runner(agent=root_agent, app_name="o2c", session_service=session_service)
    msg = types.Content(role="user", parts=[types.Part.from_text(text=PROMPTS[scenario])])
    async for event in runner.run_async(user_id="demo", session_id="s1", new_message=msg):
        if event.content and event.content.parts:
            for p in event.content.parts:
                if p.text:
                    print(f"[{event.author}] {p.text}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "happy"))
```

- [ ] **Step 2: Manual verification (requires a real GEMINI_API_KEY)**

In terminal A: `uv run uvicorn fake_sap.app:create_app --factory --port 8001`
In terminal B: `cp .env.example .env` (fill in `GEMINI_API_KEY`), then `uv run python -m agents.o2c_agent.run_scenario credit_hold`
Expected: transcript shows the creator hitting `CREDIT_BLOCK`, calling `release_credit_block`, retrying delivery, completing the chain; reviewer prints a document-flow summary with a non-zero invoice.

- [ ] **Step 3: Commit**

```bash
git add agents/o2c_agent/run_scenario.py
git commit -m "feat(agents): runnable scenario script via ADK Runner"
```

---

## Task 14: ADK evalset for the four scenarios

**Files:**
- Create: `agents/o2c_agent/eval/o2c.evalset.json`
- Create: `agents/o2c_agent/eval/test_config.json`

> This task uses ADK's eval harness. Consult the `google-agents-cli-eval` skill for the exact evalset schema before authoring; the structure below is the expected shape. Because evals call the real LLM, they run only when `GEMINI_API_KEY` is set and Fake-SAP is running.

- [ ] **Step 1: Create `agents/o2c_agent/eval/test_config.json`**

```json
{
  "criteria": {
    "tool_trajectory_avg_score": 0.6,
    "response_match_score": 0.4
  }
}
```

- [ ] **Step 2: Create `agents/o2c_agent/eval/o2c.evalset.json`**

Author one eval case per scenario. Each case's `final_response` reference should mention the expected outcome keyword so `response_match_score` can grade it: `happy` → final invoice 500; `credit_hold` → "credit" + 500; `out_of_stock` → "partial"/"backorder"; `missing_pricing` → "pricing" + 250. Use the prompts from `run_scenario.py` as the user content. Follow the exact JSON schema from the `google-agents-cli-eval` skill (`eval_set_id`, `eval_cases[].conversation[].user_content/final_response`, `session_input`).

- [ ] **Step 3: Run the eval (manual, needs key + running Fake-SAP)**

Run: `uv run adk eval agents/o2c_agent agents/o2c_agent/eval/o2c.evalset.json --config_file_path agents/o2c_agent/eval/test_config.json`
Expected: all four cases pass the configured thresholds. If a case fails, use the eval-fix loop from the `google-agents-cli-eval` skill (adjust prompts in Task 11, not the thresholds).

- [ ] **Step 4: Commit**

```bash
git add agents/o2c_agent/eval/
git commit -m "test(agents): ADK evalset covering all four O2C scenarios"
```

---

## Task 15: Web gateway (backend)

**Files:**
- Create: `web/server.py`
- Test: `web/tests/test_gateway.py`

The web app serves the static UI and two JSON endpoints, both keyed by `scenario`:
- `POST /api/rpa/run` → runs the RPA bot in-process against `FAKE_SAP_BASE_URL`, returns its step log.
- `POST /api/agent/run` → runs the agent via the ADK `Runner` and returns the transcript (list of `{author, text}`).
- `POST /api/reset` → re-seeds Fake-SAP by calling a reset endpoint (added below).

To keep RPA and agent runs isolated and reproducible per demo click, add a `POST {SO}/Reset` admin endpoint to Fake-SAP (re-seeds the store). Both panes call reset before running.

- [ ] **Step 1: Add reset endpoint to `fake_sap/app.py`** (inside `create_app`, after master-data routes)

```python
    @app.post(f"{SO}/Reset")
    async def reset_store():
        seed_store(store)
        return {"d": {"status": "reset"}}
```

- [ ] **Step 2: Write the failing test** (`web/tests/test_gateway.py`)

The gateway's RPA path is deterministic and offline-safe; the agent path needs an LLM, so the test covers RPA + reset only.

```python
import httpx
import pytest
from starlette.testclient import TestClient
import web.server as web
from fake_sap.app import create_app
from mcp_server.sap_client import SapClient


@pytest.fixture
def client(monkeypatch):
    # Point the gateway's RPA client at an in-process Fake-SAP.
    transport = httpx.ASGITransport(app=create_app())
    sap = SapClient(base_url="http://sap", http=httpx.Client(transport=transport, base_url="http://sap"))
    monkeypatch.setattr(web, "get_rpa_client", lambda: sap)
    return TestClient(web.app)


def test_rpa_run_happy(client):
    r = client.post("/api/rpa/run", json={"scenario": "happy"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["invoice_total"] == 500.0


def test_rpa_run_credit_hold_escalates(client):
    r = client.post("/api/rpa/run", json={"scenario": "credit_hold"})
    assert r.json()["status"] == "ESCALATED"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest web/tests/test_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.server'`

- [ ] **Step 4: Implement `web/server.py`**

```python
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mcp_server.sap_client import SapClient
from rpa_bot.bot import run_rpa

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="RPA vs Agentic O2C demo")


def get_rpa_client() -> SapClient:
    return SapClient(base_url=os.environ.get("FAKE_SAP_BASE_URL", "http://127.0.0.1:8001"))


def _reset() -> None:
    get_rpa_client()._post("/sap/opu/odata/sap/API_SALES_ORDER_SRV/Reset", {})


@app.post("/api/reset")
async def reset():
    _reset()
    return {"status": "reset"}


@app.post("/api/rpa/run")
async def rpa_run(request: Request):
    body = await request.json()
    _reset()
    return run_rpa(body["scenario"], get_rpa_client())


@app.post("/api/agent/run")
async def agent_run(request: Request):
    body = await request.json()
    _reset()
    from agents.o2c_agent.run_scenario import PROMPTS
    from agents.o2c_agent.agent import root_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    session_service = InMemorySessionService()
    await session_service.create_session(app_name="o2c", user_id="web", session_id="web1")
    runner = Runner(agent=root_agent, app_name="o2c", session_service=session_service)
    msg = types.Content(role="user", parts=[types.Part.from_text(text=PROMPTS[body["scenario"]])])
    transcript = []
    async for event in runner.run_async(user_id="web", session_id="web1", new_message=msg):
        if event.content and event.content.parts:
            for p in event.content.parts:
                if p.text:
                    transcript.append({"author": event.author, "text": p.text})
    return {"transcript": transcript}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest web/tests/test_gateway.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add fake_sap/app.py web/server.py web/tests/test_gateway.py
git commit -m "feat(web): gateway for RPA and agent runs + Fake-SAP reset"
```

---

## Task 16: Side-by-side web UI (frontend)

**Files:**
- Create: `web/static/index.html`
- Create: `web/static/app.js`
- Create: `web/static/style.css`

> For a more polished look you may invoke the `frontend-design` skill, but the functional version below is sufficient and self-contained.

- [ ] **Step 1: Create `web/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RPA vs Multi-Agent — SAP O2C</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <header>
    <h1>SAP Order-to-Cash: RPA vs Multi-Agent</h1>
    <div class="controls">
      <label for="scenario">Scenario</label>
      <select id="scenario">
        <option value="happy">Happy path</option>
        <option value="credit_hold">Customer on credit hold</option>
        <option value="out_of_stock">Material out of stock</option>
        <option value="missing_pricing">Missing pricing</option>
      </select>
      <button id="run">Run both</button>
    </div>
  </header>
  <main>
    <section class="pane rpa">
      <h2>Classic RPA bot</h2>
      <div id="rpa-status" class="status"></div>
      <ol id="rpa-steps"></ol>
    </section>
    <section class="pane agent">
      <h2>Multi-agent system</h2>
      <div id="agent-status" class="status"></div>
      <div id="agent-transcript"></div>
    </section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `web/static/style.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: #0f1115; color: #e6e6e6; }
header { padding: 16px 24px; border-bottom: 1px solid #262a33; }
h1 { font-size: 18px; margin: 0 0 12px; }
.controls { display: flex; gap: 12px; align-items: center; }
select, button { padding: 8px 12px; border-radius: 6px; border: 1px solid #333; background: #1a1d24; color: #e6e6e6; }
button { cursor: pointer; background: #2d6cdf; border-color: #2d6cdf; }
main { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 24px; }
.pane { background: #161922; border: 1px solid #262a33; border-radius: 8px; padding: 16px; min-height: 60vh; }
.pane h2 { margin-top: 0; font-size: 15px; }
.status { font-weight: 600; margin-bottom: 12px; }
.status.ok { color: #43c463; } .status.fail { color: #e5544b; } .status.warn { color: #e0a83d; }
#rpa-steps li { margin: 4px 0; }
#rpa-steps li.fail { color: #e5544b; } #rpa-steps li.ok { color: #43c463; }
#agent-transcript div { margin: 8px 0; padding: 8px 10px; background: #1a1d24; border-radius: 6px; white-space: pre-wrap; }
#agent-transcript .author { font-size: 11px; opacity: .6; text-transform: uppercase; }
```

- [ ] **Step 3: Create `web/static/app.js`**

```javascript
const $ = (id) => document.getElementById(id);

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

function renderRpa(res) {
  const statusEl = $("rpa-status");
  if (res.status === "COMPLETED" && res.invoice_total === 0) {
    statusEl.textContent = `⚠ COMPLETED but invoice = $0 (silently wrong)`;
    statusEl.className = "status warn";
  } else if (res.status === "COMPLETED") {
    statusEl.textContent = `✓ COMPLETED — invoice $${res.invoice_total}`;
    statusEl.className = "status ok";
  } else {
    statusEl.textContent = `✗ ESCALATED at ${res.failed_step} — human needed`;
    statusEl.className = "status fail";
  }
  const ol = $("rpa-steps");
  ol.innerHTML = "";
  for (const s of res.steps) {
    const li = document.createElement("li");
    li.className = s.ok ? "ok" : "fail";
    li.textContent = `${s.ok ? "✓" : "✗"} ${s.step} (${s.detail})`;
    ol.appendChild(li);
  }
}

function renderAgent(res) {
  $("agent-status").textContent = "✓ chain handled by agents";
  $("agent-status").className = "status ok";
  const box = $("agent-transcript");
  box.innerHTML = "";
  for (const m of res.transcript) {
    const div = document.createElement("div");
    div.innerHTML = `<div class="author">${m.author}</div>${m.text}`;
    box.appendChild(div);
  }
}

$("run").addEventListener("click", async () => {
  const scenario = $("scenario").value;
  $("rpa-status").textContent = "running…";
  $("agent-status").textContent = "running… (LLM, may take a few seconds)";
  $("rpa-steps").innerHTML = "";
  $("agent-transcript").innerHTML = "";
  const [rpa, agent] = await Promise.all([
    post("/api/rpa/run", { scenario }),
    post("/api/agent/run", { scenario }),
  ]);
  renderRpa(rpa);
  renderAgent(agent);
});
```

- [ ] **Step 4: Manual verification**

Terminal A: `uv run uvicorn fake_sap.app:create_app --factory --port 8001`
Terminal B (with `.env` containing `GEMINI_API_KEY`): `uv run uvicorn web.server:app --port 8000`
Open `http://127.0.0.1:8000`, pick "Customer on credit hold", click "Run both".
Expected: left pane shows RPA escalating at `create_outbound_delivery`; right pane shows the agents releasing the credit block and completing with a $500 invoice.

- [ ] **Step 5: Commit**

```bash
git add web/static/
git commit -m "feat(web): side-by-side RPA-vs-agentic UI"
```

---

## Task 17: README, run scripts, and full-suite verification

**Files:**
- Create: `README.md`
- Create: `scripts/run_demo.sh`

- [ ] **Step 1: Create `scripts/run_demo.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Start Fake-SAP in the background, then the web app in the foreground.
uv run uvicorn fake_sap.app:create_app --factory --port 8001 &
SAP_PID=$!
trap "kill $SAP_PID" EXIT
sleep 1
uv run uvicorn web.server:app --port 8000
```

- [ ] **Step 2: Create `README.md`**

Document: what the project proves, the architecture diagram (copy from the spec), prerequisites (Python 3.11+, a Google AI Studio key), setup (`cp .env.example .env`, fill `GEMINI_API_KEY`, `uv pip install -e ".[dev]"`), how to run tests (`uv run pytest`), how to run the demo (`bash scripts/run_demo.sh` then open `http://127.0.0.1:8000`), the four scenarios and what each demonstrates, and the model-fallback note (`gemini-3.5-flash` → `gemini-flash-latest` on 404). Reference the design spec at `docs/superpowers/specs/2026-06-02-sap-rpa-replacement-o2c-design.md`.

- [ ] **Step 3: Make the script executable and run the full offline suite**

Run: `chmod +x scripts/run_demo.sh && uv run pytest -v`
Expected: PASS — all offline tests across `fake_sap`, `mcp_server`, `rpa_bot`, `agents` (build test), and `web` (RPA path). The live LLM checks (Task 13 Step 2, Task 14 Step 3, Task 16 Step 4) are manual and excluded from the unit suite.

- [ ] **Step 4: Commit**

```bash
git add README.md scripts/run_demo.sh
git commit -m "docs: README and one-command demo runner"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** Fake-SAP OData service (Tasks 2–7, +reset in 15) ✓; curated MCP server (Tasks 8–9) ✓; ADK supervisor/creator/reviewer with read/write isolation (Tasks 11–12) ✓; gemini-3.5-flash via AI Studio + config-driven model (Tasks 1, 12) ✓; brittle RPA bot (Task 10) ✓; side-by-side web UI (Tasks 15–16) ✓; four scenarios incl. exception recovery (Tasks 5–10, 13–16) ✓; tests at every layer incl. ADK evalset (Tasks 2–16) ✓; high fidelity to `API_SALES_ORDER_SRV` field names + sibling delivery/billing services (Tasks 5–7) ✓.
- **Type consistency:** `SapClient` method names match calls in `server.py`, `bot.py`, and `web/server.py`; tool names in `READ_TOOLS`/`WRITE_TOOLS` (Task 12) exactly match `@mcp.tool()` function names (Task 9); scenario keys (`happy`/`credit_hold`/`out_of_stock`/`missing_pricing`) are identical in `bot.py`, `run_scenario.py`, and the UI.
- **Known live-LLM dependencies:** Tasks 13, 14, 16 require a real `GEMINI_API_KEY` and a running Fake-SAP; they are explicitly manual. Everything else runs offline and deterministically.
- **FastMCP callable caveat:** Task 9 Step 3 documents the `.fn(...)` fallback if the installed `mcp` version wraps tool functions.
```
