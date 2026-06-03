# Fake-SAP Fidelity to Real SAP OData Specs — Design

**Date:** 2026-06-03
**Status:** Approved (design)
**Reference specs:** https://github.com/FelipeLujan/SAP-O2C-POC/tree/main/sap_api
  (`API_SALES_ORDER_SRV.json`, `API_MATERIAL_DOCUMENT_SRV.json` — official SAP
  S/4HANA OData v2 API definitions from the SAP Business Accelerator Hub)
**Builds on:** `docs/superpowers/specs/2026-06-02-sap-rpa-replacement-o2c-design.md`

## Goal

Make our simulated SAP backend and its MCP tool layer **look and behave like a
real SAP S/4HANA OData service**, so the RPA-vs-agentic demo is grounded in
authentic SAP field names, status codes, and protocol shape — and the Fake-SAP
service stays credibly "swappable for real SAP later."

We do this **without** abandoning the deliberate architectural decision from the
prior design: a small, curated, intent-level MCP server (~13 O2C tools), not a
machine-generated tool-per-endpoint surface.

## Decisions (from brainstorming)

- **MCP approach:** Keep the curated ~13-tool MCP server. Raise fidelity of the
  *payloads, field names, status codes, and error envelopes* underneath it. No
  tool-per-endpoint generation.
- **Spec usage:** Vendor both OpenAPI specs into the repo as the **schema source
  of truth** (not runtime endpoint generation).
- **Field depth:** A **realistic curated subset** (~20–30 of the most meaningful
  real fields per entity), with correct names/types/lengths — not all 93 header
  fields (avoids static-filler noise).
- **Protocol fidelity:** Add a spec-derived OData v2 **`$metadata`** (EDMX)
  document, plus the real SAP status/process fields and a fuller error envelope.
- **Out of scope:** Modelling goods issue as a real Material Document posting via
  `API_MATERIAL_DOCUMENT_SRV` (the spec is vendored for reference only).

## Non-negotiable constraints

- **Fairness of the contrast is preserved.** The RPA bot and the agents continue
  to operate on the same shared Fake-SAP state. No change to who talks to what.
- **No breaking changes to existing consumers.** The RPA bot (`rpa_bot/bot.py`),
  web gateway (`web/`), ADK agent (`agents/`), and MCP client all read a small
  set of convenience fields today: `SalesOrder`, `OutboundDelivery`, `Material`,
  `TotalNetAmount`, `RequestedQuantity`, `CreditBlock`, `PricingStatus`,
  `BillingDocument`, `SalesOrderItem`, `GoodsIssueStatus`, `ActualDeliveryQuantity`.
  These convenience fields are **kept alongside** the new authentic fields, not
  renamed. All existing tests stay green.

## Architecture

A single schema registry feeds both data serialization and `$metadata`, so the
two can never drift:

```
            fake_sap/schema.py
        (EntityType registry: property, EDM type, maxLength, key)
        property names/types for A_SalesOrder* lifted from vendored spec
                 |                                   |
                 v                                   v
        fake_sap/entities.py                 fake_sap/metadata.py
   (project store objects -> OData dicts)   (render registry -> EDMX $metadata)
                 |                                   |
                 +----------------+------------------+
                                  v
                            fake_sap/app.py
                  (routing + business rules; CSRF; errors)
                                  ^
                                  | OData HTTP
                +-----------------+------------------+
                |                                    |
           rpa_bot (direct)                  mcp_server (curated tools)
                                                     ^
                                                     | MCP stdio
                                                  ADK agents
```

## Components

### 1. Vendored specs — `sap_api/`
- `sap_api/API_SALES_ORDER_SRV.json` and `sap_api/API_MATERIAL_DOCUMENT_SRV.json`,
  copied verbatim from the reference repo.
- `sap_api/README.md` citing the SAP Business Accelerator Hub source and stating
  these are used as a schema reference, not generated into endpoints.

### 2. Schema registry — `fake_sap/schema.py` (new)
- Declares each served EntityType as an ordered list of properties:
  `(name, edm_type, max_length | None, is_key: bool)`.
- For `A_SalesOrder`, `A_SalesOrderItem`, `A_SalesOrderScheduleLine`, the property
  names/types/lengths are taken from the vendored `API_SALES_ORDER_SRV.json`
  (curated subset listed below).
- For the invented services, `A_OutbDeliveryHeader`, `A_OutbDeliveryItem`, and
  `A_BillingDocument` are hand-declared in the same shape.
- EDM types follow OData v2 (`Edm.String`, `Edm.Decimal`, `Edm.Boolean`,
  `Edm.DateTime`).

**Curated property subsets:**

- `A_SalesOrder` (key `SalesOrder`): `SalesOrder`, `SalesOrderType`,
  `SalesOrganization`, `DistributionChannel`, `OrganizationDivision`,
  `SoldToParty`, `PurchaseOrderByCustomer`, `SalesOrderDate`, `CreationDate`,
  `RequestedDeliveryDate`, `TransactionCurrency`, `TotalNetAmount`,
  `TotalCreditCheckStatus`, `DeliveryBlockReason`, `OverallDeliveryStatus`,
  `OverallOrdReltdBillgStatus`, `OverallSDProcessStatus`.
- `A_SalesOrderItem` (keys `SalesOrder`, `SalesOrderItem`): `SalesOrder`,
  `SalesOrderItem`, `Material`, `SalesOrderItemCategory`, `RequestedQuantity`,
  `RequestedQuantityUnit`, `NetAmount`, `TransactionCurrency`.
- `A_SalesOrderScheduleLine` (keys `SalesOrder`, `SalesOrderItem`,
  `ScheduleLine`): `SalesOrder`, `SalesOrderItem`, `ScheduleLine`,
  `RequestedDeliveryDate`, `ConfirmedDeliveryDate`, `ScheduleLineOrderQuantity`,
  `ConfdOrderQtyByMatlAvailCheck`, `OrderQuantityUnit`.
- `A_OutbDeliveryHeader` (key `OutboundDelivery`): `OutboundDelivery`,
  `SalesOrder`, `GoodsMovementStatus`, plus convenience `GoodsIssueStatus`.
- `A_OutbDeliveryItem` (keys `OutboundDelivery`, `DeliveryDocumentItem`):
  `OutboundDelivery`, `DeliveryDocumentItem`, `Material`,
  `ActualDeliveryQuantity`, `DeliveryQuantityUnit`.
- `A_BillingDocument` (key `BillingDocument`): `BillingDocument`,
  `OutboundDelivery`, `TotalNetAmount`, `TransactionCurrency`.

### 3. Serialization layer — `fake_sap/entities.py` (new; refactor out of `app.py`)
- Projects `store` dataclasses → OData entity dicts using the registry ordering.
- Adds the authentic fields, derived from existing state. Status-code mapping
  (single-char SAP SD status domain: `A` = not processed, `B` = partial / not OK,
  `C` = complete / OK):
  - `TotalCreditCheckStatus` = `"B"` when credit-blocked, else `"A"`.
  - `DeliveryBlockReason` = `"01"` when credit-blocked, else `""`.
  - `OverallDeliveryStatus` = `"A"` none delivered, `"B"` partial, `"C"` fully
    delivered (from related deliveries + goods-issue state).
  - `OverallOrdReltdBillgStatus` = `"A"` not invoiced, `"C"` invoiced.
  - `OverallSDProcessStatus` = overall roll-up `A`/`B`/`C`.
  - Item `SalesOrderItem` rendered as real 6-char numbers (`"000010"`,
    `"000020"`); `RequestedQuantityUnit` = `"EA"`;
    `SalesOrderItemCategory` = `"TAN"`.
  - `to_ScheduleLine` added with `ConfirmedDeliveryDate` and
    `ConfdOrderQtyByMatlAvailCheck` reflecting ATP (ties into the stock-shortage
    scenario).
- **Convenience fields kept** for back-compat: `CreditBlock`, `PricingStatus`,
  `PricingIncomplete`, `GoodsIssueStatus`, `TotalNetAmount` remain present.

### 4. `$metadata` — `fake_sap/metadata.py` (new)
- Renders the registry to an OData v2 EDMX `$metadata` XML document.
- Served at `{SO}/$metadata`, `{DLV}/$metadata`, `{BILL}/$metadata` with
  `Content-Type: application/xml`.

### 5. Error envelope — `fake_sap/odata.py`
- Extend `odata_error_body` to the full SAP v2 shape:
  `{"error": {"code", "message": {"lang","value"}, "innererror": {"errordetails": [...]}}}`.
- `SapError` codes unchanged (the MCP `HINTS` map keys off `CREDIT_BLOCK`,
  `INSUFFICIENT_STOCK`, `DOC_FLOW`, `NOT_FOUND`).

### 6. MCP server — `mcp_server/server.py`, `mcp_server/sap_client.py`
- **No new tools; no breaking signature changes.** The client passes the richer
  payloads through unchanged.
- Tool docstrings updated to reference the real SAP field/status names now
  present in responses.
- Optional, non-breaking: `create_sales_order` may gain defaulted
  `purchase_order_by_customer` / `requested_delivery_date` kwargs. Deferred to
  implementation; only if low-risk.

### 7. Seed data — `fake_sap/seed.py`, `fake_sap/store.py`
- SAP best-practice values: sales org `1710`, distribution channel `10`,
  division `00`, currency `USD`.
- `store.py` gains a few backing fields only (order date, PO-by-customer,
  currency). Status fields are computed in `entities.py`, not stored.
- Keep the credit-blocked customer and the OOS / no-pricing-condition materials
  that drive the existing scenarios.

## Data flow (unchanged in shape, richer in content)

1. RPA bot / MCP client POSTs to a real OData path (e.g.
   `POST {SO}/A_SalesOrder` with CSRF token).
2. `app.py` applies business rules, mutates `store`, calls `entities.py` to
   serialize.
3. Response carries authentic SAP fields + convenience aliases.
4. `GET {SO}/$metadata` returns EDMX describing exactly those entity types.

## Error handling

- Business-rule violations raise `SapError` → full SAP v2 error envelope with
  `innererror.errordetails`.
- MCP layer maps `sap_code` → recovery `hint` (unchanged).

## Testing

- **Existing tests stay green** (assert on convenience fields).
- New `fake_sap` tests:
  - `$metadata` is well-formed XML and declares the expected EntityTypes, keys,
    and a sample of the curated properties.
  - Serializers emit the authentic fields with correct values/types.
  - Status-code derivation across the order → delivery → billing lifecycle
    (`A`/`B`/`C` transitions; credit-block → `TotalCreditCheckStatus="B"` +
    `DeliveryBlockReason="01"`).
  - Error body includes `innererror.errordetails`.
- New `mcp_server` test: a curated tool response surfaces the new SAP fields.

## Module boundaries (isolation & clarity)

- `schema.py` — *what the entities are*. Pure data; no FastAPI, no store.
- `entities.py` — *store object → OData dict*. Depends on `schema.py` + store
  types. No HTTP.
- `metadata.py` — *registry → EDMX*. Depends on `schema.py` only.
- `app.py` — routing, CSRF, business-rule orchestration, error mapping. Shrinks
  as serialization moves out.
Each unit is independently testable with a clear interface.

## YAGNI / explicitly excluded

- No tool-per-endpoint MCP generation.
- No full 93-field header parity.
- No Material Document goods-movement modelling.
- No `$metadata` for entity sets we do not actually serve.
- No new OData query options ($filter/$expand/$select) beyond what exists.
