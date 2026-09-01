"""
Prompt Loader — builds agent prompts from base templates + category overlays.

The system uses a 2-layer approach:
1. Base templates define the structural skeleton (shared across all categories)
2. Overlays inject category-specific content (role, title patterns, summary structure, etc.)

Usage:
    from prompt_loader import build_prompt

    # Build the "full" stage prompt for competitive_landscape category
    prompt = build_prompt(
        template="base_full",
        overlay="competitive_landscape",
        mode="full"
    )
"""

import json
import os
import logging
from string import Template
from typing import Optional

logger = logging.getLogger(__name__)

# Default directory for prompt templates (relative to this file)
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "prompt_templates")


def _load_template(template_name: str) -> str:
    """Load a base template file."""
    template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.txt")
    try:
        with open(template_path, 'r', encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Template not found: {template_path}")
        raise


def _load_overlay(overlay_name: str) -> dict:
    """Load a category overlay JSON file."""
    overlay_path = os.path.join(TEMPLATES_DIR, "overlays", f"{overlay_name}.json")
    try:
        with open(overlay_path, 'r', encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Overlay not found: {overlay_path}")
        raise


def _load_examples(examples_file: str) -> str:
    """Load an examples file if referenced in the overlay."""
    examples_path = os.path.join(TEMPLATES_DIR, "examples", examples_file)
    try:
        with open(examples_path, 'r', encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Examples file not found: {examples_path}")
        return ""


def _resolve_overlay_references(overlay: dict) -> dict:
    """
    Resolve any file references in overlay values.
    If a value starts with "See " or "file:", load the referenced file.
    """
    resolved = {}
    for key, value in overlay.items():
        if isinstance(value, str) and value.startswith("See prompt_templates/examples/"):
            # Extract filename from reference like "See prompt_templates/examples/competitive_landscape_titles.txt"
            filename = value.replace("See prompt_templates/examples/", "")
            resolved[key] = _load_examples(filename)
        elif isinstance(value, str) and value.startswith("file:"):
            filename = value[5:]  # strip "file:" prefix
            resolved[key] = _load_examples(filename)
        else:
            resolved[key] = value
    return resolved


def build_prompt(template: str, overlay: str, mode: str = "full") -> str:
    """
    Build a complete agent prompt by combining a base template with a category overlay.

    The template uses Python's string.Template syntax ($variable or ${variable})
    for placeholder substitution.

    Args:
        template: Name of the base template (without .txt extension).
                  Options: "base_full", "base_insights", "base_regenerate"
        overlay: Name of the category overlay (without .json extension).
                 Options: "competitive_landscape", "deals_and_partnerships"
        mode: Execution mode — "full", "insights", or "regenerate".
              Used to select mode-specific sections from the overlay.

    Returns:
        str: The fully assembled prompt string.

    Example:
        >>> prompt = build_prompt("base_full", "competitive_landscape", "full")
        >>> print(prompt[:50])
        'You are a market research competitive intelligence...'
    """
    # Load base template
    template_str = _load_template(template)

    # Load and resolve overlay
    overlay_data = _load_overlay(overlay)
    resolved_overlay = _resolve_overlay_references(overlay_data)

    # If overlay has mode-specific overrides, merge them
    mode_overrides = resolved_overlay.pop(f"mode_{mode}", {})
    resolved_overlay.update(mode_overrides)

    # Perform substitution
    # Using safe_substitute so missing keys don't throw errors
    tmpl = Template(template_str)
    prompt = tmpl.safe_substitute(resolved_overlay)

    return prompt


def build_prompt_with_context(
    template: str,
    overlay: str,
    mode: str = "full",
    extra_context: Optional[dict] = None
) -> str:
    """
    Build a prompt with additional runtime context injected.

    This extends build_prompt() by allowing runtime values (like specific
    category names, client names, etc.) to be injected into the template
    alongside the static overlay values.

    Args:
        template: Base template name
        overlay: Category overlay name
        mode: Execution mode
        extra_context: Additional key-value pairs to substitute into the template

    Returns:
        str: The fully assembled prompt with all substitutions applied.
    """
    # Load and prepare overlay
    template_str = _load_template(template)
    overlay_data = _load_overlay(overlay)
    resolved_overlay = _resolve_overlay_references(overlay_data)

    # Merge mode-specific overrides
    mode_overrides = resolved_overlay.pop(f"mode_{mode}", {})
    resolved_overlay.update(mode_overrides)

    # Merge extra context (runtime values take precedence)
    if extra_context:
        resolved_overlay.update(extra_context)

    # Perform substitution
    tmpl = Template(template_str)
    prompt = tmpl.safe_substitute(resolved_overlay)

    return prompt


def list_available_overlays() -> list:
    """List all available category overlay names."""
    overlays_dir = os.path.join(TEMPLATES_DIR, "overlays")
    if not os.path.isdir(overlays_dir):
        return []
    return [
        f.replace(".json", "")
        for f in os.listdir(overlays_dir)
        if f.endswith(".json")
    ]


def list_available_templates() -> list:
    """List all available base template names."""
    if not os.path.isdir(TEMPLATES_DIR):
        return []
    return [
        f.replace(".txt", "")
        for f in os.listdir(TEMPLATES_DIR)
        if f.endswith(".txt")
    ]
