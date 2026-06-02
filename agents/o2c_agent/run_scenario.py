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
