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
