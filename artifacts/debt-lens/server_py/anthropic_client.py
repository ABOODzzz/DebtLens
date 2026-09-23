"""
Anthropic client setup. Used throughout the app for AI-assisted features
(advice generation, consolidation-request letters).

Routed through Replit's AI Integrations proxy (AI_INTEGRATIONS_ANTHROPIC_*),
so no personal Anthropic API key is required -- usage is billed to Replit
credits. The model is pinned to claude-sonnet-4-6 for all calls.

Split into its own module (rather than living in main.py) so route modules
like api_routes.py can import it without a circular import against main.py.
"""

import logging
import os

logger = logging.getLogger("debtlens")

ANTHROPIC_MODEL = "claude-sonnet-4-6"
anthropic_client = None

try:
    from anthropic import Anthropic

    ai_integrations_base_url = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
    ai_integrations_api_key = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")

    if ai_integrations_base_url and ai_integrations_api_key:
        anthropic_client = Anthropic(
            base_url=ai_integrations_base_url,
            api_key=ai_integrations_api_key,
        )
        logger.info("Anthropic client initialized via Replit AI Integrations proxy.")
    else:
        logger.warning(
            "AI_INTEGRATIONS_ANTHROPIC_BASE_URL / AI_INTEGRATIONS_ANTHROPIC_API_KEY "
            "are not set. AI-assisted features will be unavailable until the "
            "Anthropic AI integration is configured."
        )
except Exception as exc:  # noqa: BLE001
    logger.warning("Failed to initialize Anthropic client: %s", exc)
    anthropic_client = None
