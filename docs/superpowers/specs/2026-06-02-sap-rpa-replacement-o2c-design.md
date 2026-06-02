# SAP O2C: Replacing RPA with a Multi-Agent System — Design

**Date:** 2026-06-02
**Status:** Approved (design)
**Reference:** https://github.com/FelipeLujan/SAP-O2C-POC

## Goal

Build a runnable sample app that demonstrates a **multi-agent system can replace
classic RPA** for SAP's Order-to-Cash (O2C) process. The defining success
criterion is an explicit, *fair* **RPA-vs-agentic contrast**: the same brittle
scripted RPA bot and the agentic system run the same scenarios against the same
simulated SAP backend, and the agents succeed (by reasoning and recovering)
where the RPA bot halts.

No real SAP instance is available, so SAP is simulated.

## Decisions (from brainstorming)

- **Primary purpose:** RPA-vs-agentic contrast (show the brittle scripted flow
  alongside the agentic flow handling variation and recovery).
- **Scenario:** Full O2C chain — order → outbound delivery → goods issue →
  billing → invoice — with realistic exception paths woven in.
- **Interface:** Custom side-by-side web UI (left = RPA bot, right = agentic
  chat), both driving the same SAP stub.
- **SAP stub fidelity:** High — modeled on the reference repo's
  `API_SALES_ORDER_SRV` OpenAPI spec (entity sets, field names), extended with
  delivery and billing OData services to complete the chain. OData ceremony
  preserved (entity-set URLs, CSRF token dance, OData error envelopes) so it is
  swappable for real SAP later.
- **Agent ↔ SAP layer:** Approach B — a small **Python-native curated MCP
  server** (FastMCP) exposing ~10 O2C tools over the Fake-SAP OData service.
- **LLM:** `gemini-3.5-flash` via Google AI Studio API key, using Google ADK.
  Model/runtime config-driven via env vars.

## Key architectural principle

For the contrast to be **fair**, the RPA bot and the agents must operate on the
**same SAP state**. The RPA bot does not speak MCP (MCP is an agent/LLM
protocol) — it simulates HTTP/screen automation against SAP directly. Therefore
the SAP simulation is a **standalone Fake-SAP service** that is the shared
system-of-record; the MCP server is a thin tool layer over it for the agents
only.

## Architecture

```
┌────────────────────── Side-by-side Web UI ──────────────────────┐
│   LEFT: RPA bot run (step log)   │   RIGHT: Agentic chat         │
└─────────┬────────────────────────┴───────────────┬──────────────┘
          │ trigger run                              │ chat
          ▼                                          ▼
   ┌──────────────┐                          ┌───────────────────┐
   │  RPA bot     │                          │  ADK agents        │
   │ (scripted,   │                          │  Supervisor →      │
   │  brittle)    │                          │  Creator/Reviewer  │
   └──────┬───────┘                          └─────────┬─────────┘
          │ OData (HTTP)                                │ MCP (stdio)
          │                                             ▼
          │                                   ┌───────────────────┐
          │                                   │  SAP MCP server    │
          │                                   │ (FastMCP, ~10 O2C  │
          │                                   │  tools)            │
          │                                   └─────────┬─────────┘
          │                                             │ OData (HTTP)
          ▼                                             ▼
   ┌──────────────────────────────────────────────────────────────┐
   │   Fake-SAP service (FastAPI) — shared system-of-record         │
   │   OData-shaped: A_SalesOrder, A_OutbDeliveryHeader,            │
   │   A_BillingDocument… + CSRF + OData error envelopes            │
   │   In-memory state + business rules (credit, ATP, doc flow)     │
   └──────────────────────────────────────────────────────────────┘
```

## Components

### `fake_sap/` — FastAPI OData simulator (shared system-of-record)
Mimics three SAP S/4HANA OData services:
- `API_SALES_ORDER_SRV`: `A_SalesOrder`, `A_SalesOrderItem`,
  `A_SalesOrderPartner`, pricing elements (fields modeled on the real spec).
- `API_OUTBOUND_DELIVERY_SRV`: `A_OutbDeliveryHeader`, `A_OutbDeliveryItem`,
  goods-issue posting.
- `API_BILLING_DOCUMENT_SRV`: `A_BillingDocument`, `A_BillingDocumentItem`.

OData conventions preserved: entity-set URL paths
(`/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder`), `X-CSRF-Token: Fetch`
handshake for writes, and SAP-style error envelopes
(`{"error": {"code": ..., "message": {"value": ...}}}`).

In-memory store seeded **deterministically** with master data, including the
exception fixtures:
- one customer on **credit hold**,
- one material **out of stock**,
- one material with **missing pricing condition**.

A small rules engine enforces: credit check on order create, ATP (available-to-
promise) stock check on delivery, document-flow ordering (delivery requires an
order; billing requires posted goods issue), and pricing determination.

### `mcp_server/` — Python FastMCP SAP tool layer
~10 curated tools, each wrapping an OData call to Fake-SAP and mapping SAP
errors into **structured tool results** (`{status, sap_code, message, hint}`) so
the agent reasons instead of crashing:
`create_sales_order`, `get_sales_order`, `simulate_order` (ATP/credit
pre-check), `create_outbound_delivery`, `post_goods_issue`,
`create_billing_document`, `get_billing_document`, `get_document_flow`,
`list_customers`, `list_materials`.

### `agents/o2c_agent/` — ADK multi-agent system
On `gemini-3.5-flash`. Mirrors the reference repo's read/write isolation,
extended for the chain:
- **Supervisor** (root): interprets the request, drives the chain, routes.
- **Creator**: write/orchestration — runs order → delivery → goods issue →
  billing, and performs exception recovery.
- **Reviewer**: read-only — verifies state and summarizes the document flow.

Connects to the MCP server via `MCPToolset` (stdio). Prompts encode the
per-exception recovery policy (see Scenarios).

### `rpa_bot/` — scripted brittle RPA simulator (the "before")
Deterministic, fixed call sequence with hard-coded field mappings that assume
the happy path. Has only a bare `try/except` that logs and aborts — the
realistic RPA failure mode. Succeeds on the happy path; **halts / "escalates to
human" on any exception**. Hits the same Fake-SAP over OData.

### `web/` — side-by-side UI + gateway
FastAPI app serving a two-pane UI and a thin gateway: triggers RPA runs (left
pane) and proxies chat to the ADK Runner (right pane). A **scenario selector**
feeds the *same* scenario to both panes.

## Demo scenarios (the contrast engine)

| Scenario | RPA bot | Agentic system |
|---|---|---|
| Happy path | completes chain | completes chain |
| Customer on credit hold | create-order error → halts | checks customer, flags for credit release / proposes reduced qty, explains |
| Material out of stock | delivery fails → halts | checks ATP, proposes partial delivery / alternate material, continues |
| Missing pricing | wrong/zero price or halt | detects, applies condition, proceeds |

## Data & error flow

- Fake-SAP returns proper OData error envelopes with SAP-ish codes.
- MCP tools convert these to structured results — never raw exceptions — so the
  agent can branch on them.
- Agent prompts encode recovery policy per exception type.
- RPA bot logs and aborts.

Happy-path agentic flow: user picks scenario → chat → Supervisor → Creator →
MCP tools → OData to Fake-SAP → order → delivery → goods issue → billing →
invoice → Reviewer summarizes document flow → UI shows completed chain.

## Testing strategy

- **Fake-SAP:** pytest for business rules (credit, ATP, doc-flow ordering,
  pricing) and OData error shapes.
- **MCP tools:** tested against Fake-SAP via TestClient — correct mapping of
  success and each error.
- **Agents:** ADK evalset (happy path + 3 exceptions) asserting final state and
  tool trajectory.
- **RPA bot:** tests proving it succeeds on the happy path and fails predictably
  on each exception, so the contrast is guaranteed.

## Repo layout

```
sap_rpa_v1/
  fake_sap/      app.py odata.py store.py rules.py seed.py  tests/
  mcp_server/    server.py sap_client.py tools.py           tests/
  agents/o2c_agent/  agent.py prompts.py __init__.py   eval/
  rpa_bot/       bot.py                                      tests/
  web/           server.py  static/{index.html,app.js,style.css}
  docs/  .env.example  pyproject.toml  README.md
```

## Configuration

`.env` (config-driven, swappable runtime):
- `GEMINI_API_KEY` — Google AI Studio key
- `GEMINI_MODEL=gemini-3.5-flash`
- `FAKE_SAP_BASE_URL` — base URL of the Fake-SAP service

## Out of scope (YAGNI)

- Real SAP connectivity / authentication beyond the OData shape.
- The full ~90 endpoints of `API_SALES_ORDER_SRV` — only the ~10 the chain needs.
- Persistent storage (in-memory store with deterministic seed is sufficient).
- Production deployment, auth, multi-user sessions.
