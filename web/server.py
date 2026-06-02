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
