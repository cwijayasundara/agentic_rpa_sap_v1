# SAP O2C RPA Replacement — Multi-Agent Demo

This project proves that a multi-agent system built with Google ADK and `gemini-3.5-flash` can replace a classic SAP Order-to-Cash (O2C) RPA bot. A brittle scripted bot and the agentic system run the same four scenarios against the same simulated SAP backend; the agents recover from credit holds, stock shortages, and missing pricing conditions where the RPA bot either halts with an escalation or, worse, silently completes with a wrong result (a $0 invoice). The comparison is fair because both paths share a single Fake-SAP instance as the system of record.

---

## Architecture

```
                        +------------------+
                        |     Web UI       |  http://127.0.0.1:8080
                        | (side-by-side)   |
                        +--------+---------+
                                 |
               +-----------------+-----------------+
               |                                   |
       +--------+--------+               +---------+--------+
       |   RPA Bot        |               |   ADK Agents     |
       | (brittle script, |               |  Supervisor →    |
       |  no recovery)    |               |  Creator +       |
       +--------+---------+               |  Reviewer        |
                |                         +--------+---------+
                |                                  |
                |                         +--------+---------+
                |                         |   MCP Server     |
                |                         | (~13 O2C tools,  |
                |                         |  stdio transport)|
                |                         +--------+---------+
                |                                  |
                +----------------------------------+
                                 |
                    +------------+------------+
                    |   Fake-SAP OData v2     |
                    |  (FastAPI simulator,    |
                    |   shared system-of-     |
                    |   record, port 8001)    |
                    +-------------------------+
```

Both the RPA bot and the ADK agents ultimately write to and read from the same Fake-SAP instance, so the comparison is fair. Only the agents go through the MCP server — the RPA bot talks to Fake-SAP directly over OData HTTP. The MCP tool_filter enforces read/write isolation between the Creator and Reviewer sub-agents.

---

## Scenarios

| Scenario | RPA Outcome | Agent Outcome |
|---|---|---|
| Happy path | Completes the full O2C chain | Completes the full O2C chain |
| Customer on credit hold (customer 1000002) | Escalates at delivery; halts | Calls `release_credit_block`, then completes with a $500 invoice |
| Material out of stock (MZ-FG-OOS, stock 3, qty 10) | Escalates at goods issue; halts | Creates a partial delivery of 3 units, notes backorder for remainder |
| Missing pricing (MZ-FG-NP) | "Completes" with a $0 invoice (silently wrong) | Applies a pricing condition (price 25), bills $250 correctly |

---

## Prerequisites

- Python 3.11 or later (the project is developed with 3.12 via `uv`)
- [`uv`](https://docs.astral.sh/uv/) — fast Python package manager
- A Google AI Studio API key (`GEMINI_API_KEY` and `GOOGLE_API_KEY`) — required only for the agentic pane and eval; all offline tests pass without it

---

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd sap_rpa_v1

# 2. Copy the example env file and fill in your API key
cp .env.example .env
# Edit .env: set GEMINI_API_KEY and GOOGLE_API_KEY

# 3. Create the virtual environment and install dependencies
uv venv --python 3.12
uv pip install -e ".[dev]"
```

---

## Running the Tests

The offline test suite covers Fake-SAP, the MCP server, the RPA bot, the web gateway, and the agent build. No API key is needed.

```bash
uv run pytest -v
```

Expected: approximately 39 tests pass (fake_sap ~25, mcp_server ~6, rpa_bot ~4, web ~2, agents build ~2).

The agentic live-run scenarios and the eval are **not** part of `pytest` — they require a valid `GEMINI_API_KEY` and a running Fake-SAP instance. They will not appear as pytest failures.

---

## Running the Demo

The demo starts Fake-SAP (port 8001) and the side-by-side web UI (port 8080) with a single command. Override ports with `SAP_PORT` / `WEB_PORT` env vars if either is in use:

```bash
bash scripts/run_demo.sh
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080) in a browser. The left pane runs the RPA bot; the right pane runs the ADK agents. The agentic pane requires a valid `GEMINI_API_KEY` in `.env`.

### Running a single agent scenario in the terminal

Fake-SAP must already be running on port 8001 (e.g., start it separately or use the demo script). A valid `GEMINI_API_KEY` is required.

```bash
# Available scenarios: happy_path, credit_hold, out_of_stock, missing_pricing
uv run python -m agents.o2c_agent.run_scenario credit_hold
```

---

## Running the Eval (manual)

Requires a valid API key and Fake-SAP running on port 8001. Uses ADK 2.1.0 syntax:

```bash
uv run adk eval agents/o2c_agent/__init__.py \
    agents/o2c_agent/eval/o2c.evalset.json \
    --eval_metrics_config_file agents/o2c_agent/eval/test_config.json
```

---

## Model Fallback Note

The project uses `gemini-3.5-flash` by default (controlled by the `GEMINI_MODEL` environment variable). If the API returns a 404 for that model ID, set the fallback in `.env`:

```
GEMINI_MODEL=gemini-flash-latest
```

---

## Design Documents

- Design spec: [`docs/superpowers/specs/2026-06-02-sap-rpa-replacement-o2c-design.md`](docs/superpowers/specs/2026-06-02-sap-rpa-replacement-o2c-design.md)
- Implementation plan: [`docs/superpowers/plans/2026-06-02-sap-rpa-replacement-o2c.md`](docs/superpowers/plans/2026-06-02-sap-rpa-replacement-o2c.md)
