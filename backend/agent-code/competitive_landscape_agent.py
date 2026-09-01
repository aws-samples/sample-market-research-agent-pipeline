"""
Competitive Landscape Agent — analyzes competitive moves, product launches,
market positioning changes, and strategic shifts.

Refactored from clinical_agent.py. Same 3-stage execution model:
  Stage 1 (full): summary + title + keywords
  Stage 2 (insights-implications): insights + implications using KB context
  Stage 3 (regenerate): on-demand field regeneration

Uses prompt_loader to build prompts from base templates + competitive_landscape overlay.
"""

from strands import Agent
from strands.models import BedrockModel
from pydantic import BaseModel, Field
from typing import List
from strands.types.exceptions import StructuredOutputException
import json
import os

from kb_query_tool import (
    query_knowledge_customer_data,
    query_knowledge_syndicate_data,
    query_knowledge_historical_data,
    read_s3_content
)

from prompt_loader import build_prompt

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisOutput(BaseModel):
    summary: str = Field(description="Concise summary of the content")
    insights: str = Field(description="Key insights extracted from the content")
    implications: str = Field(description="Implications or impact analysis")
    title: str = Field(description="A suitable title for the content")
    keywords: List[str] = Field(description="Important keywords related to the content")


model = BedrockModel(
    model_id=os.environ.get("MODEL_INFERENCE_PROFILE")
)

# ─── Load prompts from template + overlay ────────────────────────────────────────

COMPETITIVE_FULL_PROMPT = build_prompt(
    template="base_full",
    overlay="competitive_landscape",
    mode="full"
)

COMPETITIVE_INSIGHTS_IMPLICATIONS_PROMPT = build_prompt(
    template="base_insights",
    overlay="competitive_landscape",
    mode="insights"
)

COMPETITIVE_REGENERATE_PROMPT = build_prompt(
    template="base_regenerate",
    overlay="competitive_landscape",
    mode="regenerate"
)


# ─── Stage execution logic ───────────────────────────────────────────────────────

def _run_full_stage(research_topic: str, category: str, s3_object_key: str, client: str) -> dict:
    """Stage 1: Generate summary, title, and keywords."""
    agent = Agent(
        name="CompetitiveLandscapeAgent_Full",
        model=model,
        system_prompt=COMPETITIVE_FULL_PROMPT,
        tools=[read_s3_content],
        structured_output_model=AnalysisOutput
    )

    payload = json.dumps({
        "research_topic": research_topic,
        "category": category,
        "s3_object_key": s3_object_key,
        "client": client
    })

    logger.info(f"[CompetitiveLandscape] Running full stage for topic={research_topic}, client={client}")

    try:
        response = agent(payload)
        result = json.loads(str(response))
        logger.info(f"[CompetitiveLandscape] Full stage complete: title={result.get('title', 'N/A')}")
        return result
    except StructuredOutputException as e:
        logger.error(f"[CompetitiveLandscape] Structured output error in full stage: {e}")
        raise
    except Exception as e:
        logger.error(f"[CompetitiveLandscape] Full stage failed: {type(e).__name__}: {e}")
        raise


def _run_insights_stage(research_topic: str, category: str, s3_object_key: str, client: str, existing_output: dict) -> dict:
    """Stage 2: Generate insights and implications using KB context."""
    agent = Agent(
        name="CompetitiveLandscapeAgent_Insights",
        model=model,
        system_prompt=COMPETITIVE_INSIGHTS_IMPLICATIONS_PROMPT,
        tools=[
            read_s3_content,
            query_knowledge_customer_data,
            query_knowledge_syndicate_data,
            query_knowledge_historical_data
        ],
        structured_output_model=AnalysisOutput
    )

    payload = json.dumps({
        "research_topic": research_topic,
        "category": category,
        "s3_object_key": s3_object_key,
        "client": client,
        "existing_output": existing_output
    })

    logger.info(f"[CompetitiveLandscape] Running insights stage for topic={research_topic}")

    try:
        response = agent(payload)
        result = json.loads(str(response))
        logger.info(f"[CompetitiveLandscape] Insights stage complete")
        return result
    except StructuredOutputException as e:
        logger.error(f"[CompetitiveLandscape] Structured output error in insights stage: {e}")
        raise
    except Exception as e:
        logger.error(f"[CompetitiveLandscape] Insights stage failed: {type(e).__name__}: {e}")
        raise


def _run_regenerate_stage(research_topic: str, category: str, s3_object_key: str, client: str, regenerate: dict) -> dict:
    """Stage 3: Regenerate a specific field based on user feedback."""
    agent = Agent(
        name="CompetitiveLandscapeAgent_Regenerate",
        model=model,
        system_prompt=COMPETITIVE_REGENERATE_PROMPT,
        tools=[
            read_s3_content,
            query_knowledge_customer_data,
            query_knowledge_syndicate_data,
            query_knowledge_historical_data
        ],
        structured_output_model=AnalysisOutput
    )

    payload = json.dumps({
        "research_topic": research_topic,
        "category": category,
        "s3_object_key": s3_object_key,
        "client": client,
        "existing_output": regenerate.get("existing_output", {}),
        "regenerate_field": regenerate.get("field", "insights"),
        "regenerate_prompt": regenerate.get("prompt", "")
    })

    logger.info(f"[CompetitiveLandscape] Running regenerate stage for field={regenerate.get('field')}")

    try:
        response = agent(payload)
        result = json.loads(str(response))
        logger.info(f"[CompetitiveLandscape] Regenerate stage complete")
        return result
    except StructuredOutputException as e:
        logger.error(f"[CompetitiveLandscape] Structured output error in regenerate stage: {e}")
        raise
    except Exception as e:
        logger.error(f"[CompetitiveLandscape] Regenerate stage failed: {type(e).__name__}: {e}")
        raise


# ─── Public entry point (called by orchestrator) ────────────────────────────────

def competitive_landscape_agent(research_topic: str, category: str, s3_object_key: str, client: str, mode: str, regenerate: dict | None = None) -> str:
    """
    Main entry point for the Competitive Landscape agent.

    Args:
        research_topic: The market segment/industry/competitive arena
        category: "competitive_landscape"
        s3_object_key: S3 key for the raw content to analyze
        client: Client account name (used for KB filtering)
        mode: Execution stage — "full", "insights-implications", or "regenerate"
        regenerate: (Optional) Dict with field, prompt, and existing_output for regeneration

    Returns:
        str: JSON string with the analysis output
    """
    logger.info(f"[CompetitiveLandscape] Invoked with mode={mode}, topic={research_topic}, client={client}")

    if mode == "full":
        result = _run_full_stage(research_topic, category, s3_object_key, client)

    elif mode == "insights-implications":
        # First run full to get summary/title/keywords, then run insights
        full_result = _run_full_stage(research_topic, category, s3_object_key, client)
        result = _run_insights_stage(research_topic, category, s3_object_key, client, full_result)

    elif mode == "regenerate":
        if not regenerate:
            raise ValueError("regenerate mode requires a 'regenerate' dict with field, prompt, and existing_output")
        result = _run_regenerate_stage(research_topic, category, s3_object_key, client, regenerate)

    else:
        raise ValueError(f"Unknown mode: {mode}. Expected 'full', 'insights-implications', or 'regenerate'")

    return json.dumps(result)
