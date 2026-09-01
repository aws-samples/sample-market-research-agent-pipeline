"""
Category Registry — loads enabled categories from the domain profile config.

Usage:
    from category_registry import load_category_registry, load_domain_profile

    registry = load_category_registry()
    # Returns: {"competitive_landscape": {...}, "deals_and_partnerships": {...}}

    profile = load_domain_profile()
    # Returns the full domain profile dict
"""

import json
import os
import logging

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

timeout_config = Config(read_timeout=30)


def load_domain_profile() -> dict:
    """
    Load the full domain profile from S3 (production) or local file (dev).

    Resolution order:
    1. If DOMAIN_PROFILE_S3_BUCKET and DOMAIN_PROFILE_S3_KEY env vars are set → fetch from S3
    2. If DOMAIN_PROFILE_PATH env var is set → read local file
    3. Fallback → read from ./domain_profiles/market_research.json (relative to agent-code dir)

    Returns:
        dict: The full domain profile configuration
    """
    # Try S3 first (production)
    s3_bucket = os.environ.get("DOMAIN_PROFILE_S3_BUCKET")
    s3_key = os.environ.get("DOMAIN_PROFILE_S3_KEY")

    if s3_bucket and s3_key:
        logger.info(f"Loading domain profile from S3: s3://{s3_bucket}/{s3_key}")
        try:
            s3_client = boto3.client(
                's3',
                region_name=os.environ.get('AWS_REGION', 'us-east-1'),
                config=timeout_config
            )
            response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except Exception as e:
            logger.warning(f"Failed to load domain profile from S3: {e}")
            raise

    # Try local file path
    local_path = os.environ.get(
        "DOMAIN_PROFILE_PATH",
        os.path.join(os.path.dirname(__file__), "domain_profiles", "market_research.json")
    )

    logger.info(f"Loading domain profile from local file: {local_path}")
    try:
        with open(local_path, 'r', encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Domain profile not found at: {local_path}")
        raise


def load_category_registry() -> dict:
    """
    Load enabled categories from the domain profile.

    Returns:
        dict: Mapping of category_id → category config dict.
              Example: {
                  "competitive_landscape": {
                      "id": "competitive_landscape",
                      "display_name": "Competitive Landscape",
                      "agent": "competitive_landscape_agent",
                      "description": "...",
                      "enabled": True
                  },
                  ...
              }
    """
    profile = load_domain_profile()
    categories = profile.get("categories", [])
    return {cat["id"]: cat for cat in categories if cat.get("enabled", False)}


def get_enabled_category_ids() -> list:
    """
    Get a simple list of enabled category IDs.

    Returns:
        list: e.g. ["competitive_landscape", "deals_and_partnerships"]
    """
    registry = load_category_registry()
    return list(registry.keys())


def get_enabled_category_descriptions() -> dict:
    """
    Get category IDs mapped to their descriptions (useful for categorization prompts).

    Returns:
        dict: e.g. {"competitive_landscape": "Competitor moves, ...", "deals_and_partnerships": "M&A activity, ..."}
    """
    registry = load_category_registry()
    return {cat_id: cat["description"] for cat_id, cat in registry.items()}


def get_data_sources() -> dict:
    """
    Get enabled data source configurations.

    Returns:
        dict: Only enabled data sources with their configs
    """
    profile = load_domain_profile()
    sources = profile.get("data_sources", {})
    return {name: config for name, config in sources.items() if config.get("enabled", False)}


def get_terminology() -> dict:
    """
    Get the UI terminology labels for the current domain profile.

    Returns:
        dict: e.g. {"topic_label": "Research Topic", "customer_label": "Client Account", ...}
    """
    profile = load_domain_profile()
    return profile.get("terminology", {})
