from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands.tools.executors import SequentialToolExecutor
from pydantic import BaseModel, Field
from typing import List

from category_registry import load_category_registry, get_enabled_category_ids

# Import category agents (1:1 mapping)
from competitive_landscape_agent import competitive_landscape_agent as competitive_subagent
from deals_partnerships_agent import deals_partnerships_agent as deals_subagent

import json
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisOutput(BaseModel):
    summary: str = Field(description="Exact summary as returned by the sub-agent tool. Do not modify.")
    insights: str = Field(default="", description="Exact insights as returned by the sub-agent tool. Can be empty string. Do not generate or fill in if empty.")
    implications: str = Field(default="", description="Exact implications as returned by the sub-agent tool. Can be empty string. Do not generate or fill in if empty.")
    title: str = Field(description="Exact title as returned by the sub-agent tool. Do not modify.")
    keywords: List[str] = Field(description="Exact keywords list as returned by the sub-agent tool. Do not modify.")


# ─── Wrap sub-agents as tools ───────────────────────────────────────────────────

@tool
def competitive_landscape_agent(research_topic: str, category: str, s3_object_key: str, client: str, mode: str, regenerate: dict | None = None):
    """
    Use this tool when category is competitive_landscape.
    Analyzes competitive moves, product launches, market positioning, and strategic shifts.
    Returns structured analysis output.
    """
    result = competitive_subagent(research_topic, category, s3_object_key, client, mode, regenerate)
    return result


@tool
def deals_partnerships_agent(research_topic: str, category: str, s3_object_key: str, client: str, mode: str, regenerate: dict | None = None):
    """
    Use this tool when category is deals_and_partnerships.
    Analyzes M&A activity, licensing deals, co-development agreements, and joint ventures.
    Returns structured analysis output.
    """
    result = deals_subagent(research_topic, category, s3_object_key, client, mode, regenerate)
    return result


# ─── Orchestrator Setup ─────────────────────────────────────────────────────────

model = BedrockModel(
    model_id=os.environ.get("MODEL_INFERENCE_PROFILE")
)

# Build orchestrator prompt dynamically from category registry
enabled_categories = get_enabled_category_ids()
categories_str = ", ".join(enabled_categories)

ORCHESTRATOR_AGENT_PROMPT = f"""
You are a routing agent. You do NOT generate any content yourself.

Your ONLY task:
1. Read the input JSON and extract the "category" field.
2. Route to the matching category agent tool:
   - If category = "competitive_landscape" → call the competitive_landscape_agent tool with ALL input fields.
   - If category = "deals_and_partnerships" → call the deals_partnerships_agent tool with ALL input fields.
3. Return the tool's output EXACTLY as-is. Do NOT change a single character.

Available categories: {categories_str}

STRICT PROHIBITIONS:
- Do NOT generate, rewrite, summarize, or add any text of your own.
- Do NOT fill in, modify, or enhance any field values from the sub-agent output.
- Do NOT add markdown formatting, code blocks, backticks, or any wrapping.
- Do NOT add explanations, commentary, or metadata before or after the output.
- If any field is an empty string "", return it as an empty string. NEVER populate it.
- Your response must contain ONLY the raw JSON object returned by the sub-agent tool. Nothing else.
"""

# ─── Agent Map (for programmatic routing if needed) ─────────────────────────────

AGENT_MAP = {
    "competitive_landscape": competitive_landscape_agent,
    "deals_and_partnerships": deals_partnerships_agent,
}

# ─── Application Entry Point ────────────────────────────────────────────────────

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    print("=== orchestrator agent started ===", flush=True)
    print(f"Received payload: {payload}", flush=True)

    try:
        # Create agent per request (stateless), model is reused
        orchestrator = Agent(
            name="OrchestratorAgent",
            model=model,
            system_prompt=ORCHESTRATOR_AGENT_PROMPT,
            tool_executor=SequentialToolExecutor(),
            tools=list(AGENT_MAP.values()),
            structured_output_model=AnalysisOutput
        )

        payload_str = json.dumps(payload)
        print(f"Invoking orchestrator...", flush=True)

        response = orchestrator(payload_str)

        print(f"Orchestrator response received: {response}", flush=True)
        return str(response)

    except Exception as e:
        print(f"Invoke failed: {type(e).__name__}: {e}", flush=True)
        raise


if __name__ == "__main__":
    app.run()
