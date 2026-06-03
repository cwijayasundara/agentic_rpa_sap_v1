# Fake-SAP Real-Spec Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Fake-SAP and its curated MCP tools present authentic SAP S/4HANA OData field names, status codes, a spec-derived `$metadata` document, and a fuller error envelope — without breaking any existing consumer or test.

**Architecture:** A single schema registry (`fake_sap/schema.py`) declares each served EntityType; it feeds both a new serialization layer (`fake_sap/entities.py`) and a new `$metadata` renderer (`fake_sap/metadata.py`). `app.py` shrinks to routing + business rules. Convenience fields current consumers read are kept as additive aliases; monetary fields stay numeric for back-compat.

**Tech Stack:** Python 3.11+, FastAPI/Starlette, httpx, pytest (`uv run pytest`), MCP (FastMCP). Vendored SAP OpenAPI specs in `sap_api/`.

**Reference spec:** `docs/superpowers/specs/2026-06-03-sap-fidelity-real-specs-design.md`

**Baseline:** 42 tests passing before any change.

---

## File Structure

- Create: `sap_api/API_SALES_ORDER_SRV.json`, `sap_api/API_MATERIAL_DOCUMENT_SRV.json`, `sap_api/README.md` — vendored spec source of truth.
- Create: `fake_sap/schema.py` — EntityType/Service registry. Pure data; no FastAPI, no store.
- Create: `fake_sap/metadata.py` — renders the registry to OData v2 EDMX `$metadata`. Depends on `schema.py` only.
- Create: `fake_sap/entities.py` — projects `store` objects to OData dicts (authentic fields + convenience aliases + status derivation). Depends on `schema.py` and store types.
- Modify: `fake_sap/odata.py` — fuller SAP error envelope.
- Modify: `fake_sap/store.py` — add one backing field (`purchase_order_by_customer`).
- Modify: `fake_sap/app.py` — use `entities.py` serializers; add `$metadata` routes; thread `PurchaseOrderByCustomer` on create.
- Modify: `mcp_server/sap_client.py`, `mcp_server/server.py` — optional PO param + docstrings (no breaking change).
- Create tests: `fake_sap/tests/test_schema.py`, `test_metadata.py`, `test_entities.py`, `test_error_envelope.py`; extend `mcp_server/tests/test_tools.py`.

**Status-code convention (SAP SD single-char domain):** `A` = not processed / not relevant, `B` = partial / not OK, `C` = complete / OK.

---

### Task 1: Vendor the SAP OpenAPI specs

**Files:**
- Create: `sap_api/API_SALES_ORDER_SRV.json`
- Create: `sap_api/API_MATERIAL_DOCUMENT_SRV.json`
- Create: `sap_api/README.md`

- [ ] **Step 1: Download both specs from the reference repo**

Run:
```bash
mkdir -p sap_api
gh api repos/FelipeLujan/SAP-O2C-POC/contents/sap_api/API_SALES_ORDER_SRV.json --jq '.content' | base64 -d > sap_api/API_SALES_ORDER_SRV.json
gh api repos/FelipeLujan/SAP-O2C-POC/contents/sap_api/API_MATERIAL_DOCUMENT_SRV.json --jq '.content' | base64 -d > sap_api/API_MATERIAL_DOCUMENT_SRV.json
```

- [ ] **Step 2: Verify the files are valid JSON with the expected titles**

Run:
```bash
uv run python -c "import json; print(json.load(open('sap_api/API_SALES_ORDER_SRV.json'))['info']['title']); print(json.load(open('sap_api/API_MATERIAL_DOCUMENT_SRV.json'))['info']['title'])"
```
Expected output:
```
Sales Order (A2X)
Material Documents - Read, Create
```

- [ ] **Step 3: Write `sap_api/README.md`**

```markdown
# Vendored SAP OData API specifications

These are official SAP S/4HANA Cloud OData v2 API definitions, used as the
**schema source of truth** for the Fake-SAP simulator's field names, types, and
status codes. They are referenced (not generated into runtime endpoints).

| File | SAP service | Source |
|---|---|---|
| `API_SALES_ORDER_SRV.json` | Sales Order (A2X) | SAP Business Accelerator Hub |
| `API_MATERIAL_DOCUMENT_SRV.json` | Material Documents – Read, Create | SAP Business Accelerator Hub |

Originally mirrored from the reference repo
<https://github.com/FelipeLujan/SAP-O2C-POC/tree/main/sap_api>.

`API_MATERIAL_DOCUMENT_SRV.json` is vendored for reference only; goods-movement
postings are not modelled against it (see the design doc).
```

- [ ] **Step 4: Commit**

```bash
git add sap_api/
git commit -m "chore(sap): vendor SAP Sales Order + Material Document OData specs as schema source"
```

---

### Task 2: Schema registry — `fake_sap/schema.py`

**Files:**
- Create: `fake_sap/schema.py`
- Test: `fake_sap/tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# fake_sap/tests/test_schema.py
from fake_sap import schema


def test_sales_order_has_key_and_credit_status_field():
    et = schema.A_SALES_ORDER
    assert et.name == "A_SalesOrder"
    keys = [p.name for p in et.properties if p.is_key]
    assert keys == ["SalesOrder"]
    by_name = {p.name: p for p in et.properties}
    assert by_name["TotalCreditCheckStatus"].edm_type == "Edm.String"
    assert by_name["TotalCreditCheckStatus"].max_length == 1
    assert by_name["TotalNetAmount"].edm_type == "Edm.Decimal"


def test_item_has_composite_key():
    keys = [p.name for p in schema.A_SALES_ORDER_ITEM.properties if p.is_key]
    assert keys == ["SalesOrder", "SalesOrderItem"]


def test_services_registry_covers_three_services():
    assert set(schema.SERVICES) == {
        "API_SALES_ORDER_SRV",
        "API_OUTBOUND_DELIVERY_SRV",
        "API_BILLING_DOCUMENT_SRV",
    }
    so = schema.SERVICES["API_SALES_ORDER_SRV"]
    set_names = [name for name, _ in so.entity_sets]
    assert set_names == [
        "A_SalesOrder", "A_SalesOrderItem", "A_SalesOrderScheduleLine",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fake_sap.schema'`

- [ ] **Step 3: Write `fake_sap/schema.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_schema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add fake_sap/schema.py fake_sap/tests/test_schema.py
git commit -m "feat(fake-sap): add EntityType/Service schema registry from SAP specs"
```

---

### Task 3: `$metadata` renderer — `fake_sap/metadata.py`

**Files:**
- Create: `fake_sap/metadata.py`
- Test: `fake_sap/tests/test_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
# fake_sap/tests/test_metadata.py
import xml.etree.ElementTree as ET
from fake_sap import metadata, schema


def test_render_is_well_formed_xml():
    xml = metadata.render_metadata(schema.SALES_ORDER_SERVICE)
    # parses without error
    ET.fromstring(xml)
    assert xml.startswith("<?xml")


def test_render_declares_entity_types_keys_and_sets():
    xml = metadata.render_metadata(schema.SALES_ORDER_SERVICE)
    assert 'EntityType Name="A_SalesOrderType"' in xml
    assert '<PropertyRef Name="SalesOrder"/>' in xml
    assert 'Property Name="TotalCreditCheckStatus" Type="Edm.String" MaxLength="1"' in xml
    assert 'EntitySet Name="A_SalesOrder" EntityType="API_SALES_ORDER_SRV.A_SalesOrderType"' in xml


def test_decimal_property_has_no_maxlength():
    xml = metadata.render_metadata(schema.SALES_ORDER_SERVICE)
    assert '<Property Name="TotalNetAmount" Type="Edm.Decimal" Nullable="true"/>' in xml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fake_sap.metadata'`

- [ ] **Step 3: Write `fake_sap/metadata.py`**

```python
from __future__ import annotations
from fake_sap.schema import EntityType, Service

_EDMX_OPEN = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<edmx:Edmx Version="1.0" '
    'xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">\n'
    ' <edmx:DataServices '
    'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" '
    'm:DataServiceVersion="2.0">\n'
)
_EDMX_CLOSE = " </edmx:DataServices>\n</edmx:Edmx>\n"


def _property_xml(prop) -> str:
    attrs = f'Name="{prop.name}" Type="{prop.edm_type}"'
    if prop.max_length is not None:
        attrs += f' MaxLength="{prop.max_length}"'
    attrs += ' Nullable="false"' if prop.is_key else ' Nullable="true"'
    return f"      <Property {attrs}/>"


def _entity_type_xml(et: EntityType) -> str:
    keys = [p for p in et.properties if p.is_key]
    key_refs = "".join(f'<PropertyRef Name="{p.name}"/>' for p in keys)
    props = "\n".join(_property_xml(p) for p in et.properties)
    return (
        f'    <EntityType Name="{et.name}Type">\n'
        f"      <Key>{key_refs}</Key>\n"
        f"{props}\n"
        f"    </EntityType>"
    )


def render_metadata(service: Service) -> str:
    ns = service.namespace
    types = "\n".join(_entity_type_xml(et) for _, et in service.entity_sets)
    sets = "\n".join(
        f'      <EntitySet Name="{name}" '
        f'EntityType="{ns}.{et.name}Type"/>'
        for name, et in service.entity_sets
    )
    schema_xml = (
        f'  <Schema Namespace="{ns}" '
        'xmlns="http://schemas.microsoft.com/ado/2008/09/edm">\n'
        f"{types}\n"
        f'    <EntityContainer Name="{ns}_Entities" '
        'm:IsDefaultEntityContainer="true">\n'
        f"{sets}\n"
        "    </EntityContainer>\n"
        "  </Schema>\n"
    )
    return _EDMX_OPEN + schema_xml + _EDMX_CLOSE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_metadata.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add fake_sap/metadata.py fake_sap/tests/test_metadata.py
git commit -m "feat(fake-sap): render OData v2 EDMX \$metadata from schema registry"
```

---

### Task 4: Serve `$metadata` from the app

**Files:**
- Modify: `fake_sap/app.py` (add routes near the CSRF service-root section, after `service_root`)
- Test: `fake_sap/tests/test_metadata.py` (add an HTTP test)

- [ ] **Step 1: Write the failing test (append to `test_metadata.py`)**

```python
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"


def test_metadata_endpoints_served_for_three_services():
    client = TestClient(create_app())
    for base, marker in [
        (SO, 'Name="A_SalesOrderType"'),
        (DLV, 'Name="A_OutbDeliveryHeaderType"'),
        (BILL, 'Name="A_BillingDocumentType"'),
    ]:
        r = client.get(f"{base}/$metadata")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/xml")
        assert marker in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_metadata.py::test_metadata_endpoints_served_for_three_services -v`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Add the routes in `fake_sap/app.py`**

Add these imports near the top (with the other `from fake_sap...` imports):

```python
from fastapi.responses import Response
from fake_sap import schema
from fake_sap.metadata import render_metadata
```

Inside `create_app`, immediately after the `service_root` function block, add:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_metadata.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add fake_sap/app.py fake_sap/tests/test_metadata.py
git commit -m "feat(fake-sap): serve \$metadata at the three OData service roots"
```

---

### Task 5: Serialization layer — `fake_sap/entities.py` + refactor `app.py`

**Files:**
- Create: `fake_sap/entities.py`
- Modify: `fake_sap/store.py` (add one field)
- Modify: `fake_sap/app.py` (use the new serializers; remove inline ones)
- Test: `fake_sap/tests/test_entities.py`

- [ ] **Step 1: Add the backing field to `fake_sap/store.py`**

In the `SalesOrder` dataclass, add after `pricing_status`:

```python
    purchase_order_by_customer: str = ""
```

- [ ] **Step 2: Write the failing test**

```python
# fake_sap/tests/test_entities.py
from fake_sap.store import Store, SalesOrder, SalesOrderItem, Delivery, DeliveryItem, BillingDocument
from fake_sap import entities, schema


def _order(store, blocked=False, pricing="complete"):
    o = SalesOrder(
        sales_order="4500000000", sold_to="1000001", sales_org="1710",
        dist_channel="10", division="00",
        items=[SalesOrderItem(item="000010", material="MZ-FG-C100",
                              quantity=10, net_amount=500.0, pricing_incomplete=False)],
        credit_block=blocked, pricing_status=pricing,
        purchase_order_by_customer="PO-4711")
    store.sales_orders[o.sales_order] = o
    return o


def test_order_dict_has_authentic_fields_and_aliases():
    store = Store()
    store.materials["MZ-FG-C100"] = __import__("fake_sap.store", fromlist=["Material"]).Material(
        "MZ-FG-C100", "Pump", 100, 50.0, True)
    o = _order(store)
    d = entities.sales_order_to_dict(o, store)
    # authentic SAP fields
    assert d["SalesOrderType"] == "OR"
    assert d["TransactionCurrency"] == "USD"
    assert d["TotalCreditCheckStatus"] == "A"
    assert d["DeliveryBlockReason"] == ""
    assert d["PurchaseOrderByCustomer"] == "PO-4711"
    assert d["SalesOrderDate"].startswith("/Date(")
    # monetary stays numeric for back-compat
    assert d["TotalNetAmount"] == 500.0
    # convenience aliases preserved
    assert d["CreditBlock"] is False
    assert d["PricingStatus"] == "complete"
    # item + schedule line fidelity
    it = d["to_Item"][0]
    assert it["RequestedQuantityUnit"] == "EA"
    assert it["SalesOrderItemCategory"] == "TAN"
    sl = it["to_ScheduleLine"][0]
    assert sl["ConfdOrderQtyByMatlAvailCheck"] == 10  # 100 in stock >= 10


def test_credit_block_sets_real_status_fields():
    store = Store()
    store.materials["MZ-FG-C100"] = __import__("fake_sap.store", fromlist=["Material"]).Material(
        "MZ-FG-C100", "Pump", 100, 50.0, True)
    o = _order(store, blocked=True)
    d = entities.sales_order_to_dict(o, store)
    assert d["TotalCreditCheckStatus"] == "B"
    assert d["DeliveryBlockReason"] == "01"
    assert d["OverallSDProcessStatus"] == "B"


def test_order_dict_keys_cover_registry_properties():
    store = Store()
    store.materials["MZ-FG-C100"] = __import__("fake_sap.store", fromlist=["Material"]).Material(
        "MZ-FG-C100", "Pump", 100, 50.0, True)
    d = entities.sales_order_to_dict(_order(store), store)
    for prop in schema.A_SALES_ORDER.properties:
        assert prop.name in d, f"missing authentic field {prop.name}"


def test_delivery_and_billing_dicts():
    dlv = Delivery(delivery="8000000000", sales_order="4500000000",
                   items=[DeliveryItem(item="000010", material="MZ-FG-C100", quantity=10)],
                   goods_issue_status="C")
    dd = entities.delivery_to_dict(dlv)
    assert dd["GoodsMovementStatus"] == "C"
    assert dd["GoodsIssueStatus"] == "C"  # alias kept
    assert dd["to_Item"][0]["DeliveryQuantityUnit"] == "EA"
    bill = BillingDocument(billing_document="9000000000", delivery="8000000000",
                           total_net_amount=500.0)
    bd = entities.billing_to_dict(bill)
    assert bd["TransactionCurrency"] == "USD"
    assert bd["TotalNetAmount"] == 500.0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_entities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fake_sap.entities'`

- [ ] **Step 4: Write `fake_sap/entities.py`**

```python
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
```

- [ ] **Step 5: Run the entities test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_entities.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Refactor `fake_sap/app.py` to use the serializers**

Add the import near the other `from fake_sap...` imports:

```python
from fake_sap import entities
```

Delete the inline `_order_to_dict` function (currently lines ~30-46).

Replace each of the four `return odata_single(_order_to_dict(order))` calls with:

```python
        return odata_single(entities.sales_order_to_dict(order, store))
```

In `_register_delivery_and_billing`, delete the inline `_delivery_to_dict`
function and the `app.state._delivery_to_dict = _delivery_to_dict` line. Replace
the three `_delivery_to_dict(...)` call sites (`create_delivery`, `get_delivery`,
`post_goods_issue`) with `entities.delivery_to_dict(...)`. Update the import line
inside that function — change:

```python
    from fake_sap.store import Delivery, DeliveryItem
```
to:
```python
    from fake_sap.store import Delivery, DeliveryItem
    from fake_sap import entities
```

In `_register_billing`, replace the inline billing response dict in
`create_billing` and `get_billing` with `entities.billing_to_dict(bill)` /
`entities.billing_to_dict(b)`.

- [ ] **Step 7: Run the full suite to verify nothing broke**

Run: `uv run pytest -q`
Expected: PASS — all prior 42 tests plus the new ones (no failures). If any
existing test asserted on a removed field, it should not have — convenience
fields are preserved. Investigate any failure before continuing.

- [ ] **Step 8: Commit**

```bash
git add fake_sap/entities.py fake_sap/store.py fake_sap/app.py fake_sap/tests/test_entities.py
git commit -m "feat(fake-sap): serialize entities with authentic SAP fields + status codes"
```

---

### Task 6: Status-code lifecycle test (end-to-end via HTTP)

**Files:**
- Test: `fake_sap/tests/test_entities.py` (append HTTP lifecycle test)

- [ ] **Step 1: Write the failing test (append)**

```python
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"


def _csrf(client):
    return client.get(f"{SO}/", headers={"X-CSRF-Token": "Fetch"}).headers["X-CSRF-Token"]


def test_status_codes_progress_through_lifecycle():
    client = TestClient(create_app())
    t = _csrf(client)
    H = {"X-CSRF-Token": t}
    so = client.post(f"{SO}/A_SalesOrder", headers=H, json={
        "SoldToParty": "1000001", "SalesOrganization": "1710",
        "DistributionChannel": "10", "OrganizationDivision": "00",
        "to_Item": [{"Material": "MZ-FG-C100", "RequestedQuantity": 10}]}).json()["d"]
    assert so["OverallDeliveryStatus"] == "A"
    assert so["OverallOrdReltdBillgStatus"] == "A"
    sales_order = so["SalesOrder"]

    dlv = client.post(f"{DLV}/A_OutbDeliveryHeader", headers=H,
                      json={"SalesOrder": sales_order}).json()["d"]["OutboundDelivery"]
    after_dlv = client.get(SO + f"/A_SalesOrder('{sales_order}')").json()["d"]
    assert after_dlv["OverallDeliveryStatus"] == "B"  # delivery exists, GI not posted

    client.post(f"{DLV}/PostGoodsIssue", headers=H, json={"OutboundDelivery": dlv})
    client.post(f"{BILL}/A_BillingDocument", headers=H, json={"OutboundDelivery": dlv})
    final = client.get(SO + f"/A_SalesOrder('{sales_order}')").json()["d"]
    assert final["OverallDeliveryStatus"] == "C"
    assert final["OverallOrdReltdBillgStatus"] == "C"
    assert final["OverallSDProcessStatus"] == "C"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest fake_sap/tests/test_entities.py::test_status_codes_progress_through_lifecycle -v`
Expected: PASS (the serializers from Task 5 already implement the derivation)

- [ ] **Step 3: Commit**

```bash
git add fake_sap/tests/test_entities.py
git commit -m "test(fake-sap): assert SD status codes progress A->B->C across lifecycle"
```

---

### Task 7: Fuller SAP error envelope — `fake_sap/odata.py`

**Files:**
- Modify: `fake_sap/odata.py`
- Test: `fake_sap/tests/test_error_envelope.py`

- [ ] **Step 1: Write the failing test**

```python
# fake_sap/tests/test_error_envelope.py
from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"


def test_error_body_has_innererror_errordetails():
    client = TestClient(create_app())
    r = client.get(SO + "/A_SalesOrder('NOPE')")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["message"]["value"]
    details = err["innererror"]["errordetails"]
    assert details[0]["code"] == "NOT_FOUND"
    assert details[0]["severity"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest fake_sap/tests/test_error_envelope.py -v`
Expected: FAIL — `KeyError: 'innererror'`

- [ ] **Step 3: Update `odata_error_body` in `fake_sap/odata.py`**

```python
def odata_error_body(code: str, message: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": {"lang": "en", "value": message},
            "innererror": {
                "errordetails": [
                    {"code": code, "message": message, "severity": "error"}
                ]
            },
        }
    }
```

- [ ] **Step 4: Run the full suite (the client parses these bodies)**

Run: `uv run pytest -q`
Expected: PASS — new test passes; existing error-path tests and the MCP
client's `_handle` (which reads `error.code` / `error.message.value` /
`error.detail`) are unaffected by the additive `innererror`.

- [ ] **Step 5: Commit**

```bash
git add fake_sap/odata.py fake_sap/tests/test_error_envelope.py
git commit -m "feat(fake-sap): emit SAP v2 error envelope with innererror.errordetails"
```

---

### Task 8: MCP fidelity — optional PO param + docstrings (non-breaking)

**Files:**
- Modify: `fake_sap/app.py` (read `PurchaseOrderByCustomer` on create)
- Modify: `mcp_server/sap_client.py` (pass it through)
- Modify: `mcp_server/server.py` (optional tool param + docstrings)
- Test: `mcp_server/tests/test_tools.py` (append)

- [ ] **Step 1: Thread `PurchaseOrderByCustomer` through create in `fake_sap/app.py`**

In `create_sales_order`, where the `SalesOrder(...)` is constructed, add the
keyword argument:

```python
            pricing_status=pricing_status,
            purchase_order_by_customer=payload.get("PurchaseOrderByCustomer", ""))
```

- [ ] **Step 2: Pass it through in `mcp_server/sap_client.py`**

Change the `create_sales_order` signature and body:

```python
    def create_sales_order(self, sold_to, sales_org, dist_channel, division, items,
                           purchase_order_by_customer: str = "") -> dict:
        body = {"SoldToParty": sold_to, "SalesOrganization": sales_org,
                "DistributionChannel": dist_channel, "OrganizationDivision": division,
                "PurchaseOrderByCustomer": purchase_order_by_customer,
                "to_Item": [{"Material": i["material"], "RequestedQuantity": i["quantity"]}
                            for i in items]}
        return self._post(f"{SO}/A_SalesOrder", body)
```

- [ ] **Step 3: Update the MCP tool in `mcp_server/server.py`**

```python
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
```

- [ ] **Step 4: Write the failing test (append to `mcp_server/tests/test_tools.py`)**

```python
def test_create_order_carries_authentic_sap_fields():
    res = srv.create_sales_order("1000001", "1710", "10", "00",
                                 [{"material": "MZ-FG-C100", "quantity": 10}],
                                 purchase_order_by_customer="PO-4711")
    assert res["status"] == "success"
    assert res["SalesOrderType"] == "OR"
    assert res["TransactionCurrency"] == "USD"
    assert res["TotalCreditCheckStatus"] == "A"
    assert res["PurchaseOrderByCustomer"] == "PO-4711"
    # convenience alias still present
    assert res["CreditBlock"] is False


def test_credit_blocked_order_reports_real_status():
    res = srv.create_sales_order("1000002", "1710", "10", "00",
                                 [{"material": "MZ-FG-C100", "quantity": 10}])
    assert res["TotalCreditCheckStatus"] == "B"
    assert res["DeliveryBlockReason"] == "01"
```

- [ ] **Step 5: Run the MCP tests**

Run: `uv run pytest mcp_server/tests/test_tools.py -v`
Expected: PASS — new tests plus the unchanged existing ones.

- [ ] **Step 6: Commit**

```bash
git add fake_sap/app.py mcp_server/sap_client.py mcp_server/server.py mcp_server/tests/test_tools.py
git commit -m "feat(mcp): surface authentic SAP fields; accept optional customer PO ref"
```

---

### Task 9: Docs touch-up + final verification

**Files:**
- Modify: `README.md` (note `$metadata` + spec-derived fidelity)

- [ ] **Step 1: Add a short note to `README.md`**

Under the architecture/Fake-SAP section, add:

```markdown
### SAP fidelity

The Fake-SAP service mirrors the real SAP S/4HANA OData APIs vendored in
`sap_api/` (`API_SALES_ORDER_SRV`, `API_MATERIAL_DOCUMENT_SRV`). Entities expose
authentic field names and SD status codes (`TotalCreditCheckStatus`,
`DeliveryBlockReason`, `OverallDeliveryStatus`, `OverallOrdReltdBillgStatus`,
`OverallSDProcessStatus`; `A`/`B`/`C` = not-processed/partial/complete), and each
service serves an OData v2 `$metadata` document at e.g.
`GET /sap/opu/odata/sap/API_SALES_ORDER_SRV/$metadata`. Monetary fields are kept
numeric for demo readability; this is the one deliberate simplification vs. real
SAP (which returns decimals as strings).
```

- [ ] **Step 2: Run the entire test suite**

Run: `uv run pytest -q`
Expected: PASS — all previous 42 tests plus the new ~17 (no failures).

- [ ] **Step 3: Smoke-test `$metadata` against a live server**

Run:
```bash
uv run uvicorn fake_sap.app:create_app --factory --port 8001 &
sleep 2
curl -s http://127.0.0.1:8001/sap/opu/odata/sap/API_SALES_ORDER_SRV/\$metadata | head -20
kill %1
```
Expected: EDMX XML beginning `<?xml version="1.0" ...` with `EntityType Name="A_SalesOrderType"`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document Fake-SAP \$metadata and spec-derived field fidelity"
```

---

## Self-Review notes

- **Spec coverage:** §1 specs → Task 1; §2 registry → Task 2; §3 serializers/status → Tasks 5–6; §4 `$metadata` → Tasks 3–4; §5 error envelope → Task 7; §6 MCP fidelity → Task 8; §7 seed/store → Task 5 (store field) + Task 8 (PO); §8 testing → Tasks 2–9; docs → Task 9.
- **Back-compat:** convenience fields (`CreditBlock`, `PricingStatus`, `PricingIncomplete`, `GoodsIssueStatus`, numeric `TotalNetAmount`/`NetAmount`) preserved; existing 42 tests must stay green (verified after Tasks 5 and 7).
- **Seed best-practice org (`1710`)** is used in new tests and demo payloads only; existing master-data IDs (customers `1000001`/`1000002`, materials `MZ-FG-*`) and existing tests posting org `1010` are left untouched to avoid breakage — so no separate seed-rewrite task is needed.
- **Type consistency:** serializer fn names (`sales_order_to_dict`, `sales_order_item_dict`, `delivery_to_dict`, `billing_to_dict`, `render_metadata`) are referenced identically across `app.py` and tests; `Service.entity_sets` is a tuple of `(set_name, EntityType)` everywhere.
