"""Configuration for the dependency-upgrade webhook service.

All values are read from environment variables. Sensible placeholders are used
when a variable is not set so the script can be imported/run for local testing
without any real credentials.
"""
from __future__ import annotations

import os

# Logging level for application diagnostics (DEBUG, INFO, WARNING, ERROR, CRITICAL).
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Devin API
# ---------------------------------------------------------------------------
# Base URL for the Devin REST API.
DEVIN_API_BASE_URL: str = os.getenv("DEVIN_API_BASE_URL", "https://api.devin.ai")

# Devin API key (Service User API Key or Personal Access Token, "cog_" prefix).
# PLACEHOLDER — replace via the DEVIN_API_KEY environment variable.
DEVIN_API_KEY: str = os.getenv("DEVIN_API_KEY", "cog_REPLACE_ME_WITH_YOUR_DEVIN_API_KEY")

# ---------------------------------------------------------------------------
# Target code repository
# ---------------------------------------------------------------------------
# The repository the Devin session should operate on when performing the
# dependency upgrade.
# PLACEHOLDER — replace via the TARGET_REPO_URL environment variable.
TARGET_REPO_URL: str = os.getenv(
    "TARGET_REPO_URL", "https://github.com/your-org/your-repo"
)

# ---------------------------------------------------------------------------
# GitHub webhook
# ---------------------------------------------------------------------------
# Shared secret configured on the GitHub webhook. Used to verify the
# X-Hub-Signature-256 header. If empty, signature verification is skipped
# (NOT recommended for production).
GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# The issue label that triggers a Devin session.
TRIGGER_LABEL: str = os.getenv("TRIGGER_LABEL", "dependency_upgrade")

# Optional cap on ACUs the triggered session may consume. Empty => no limit.
_max_acu = os.getenv("DEVIN_MAX_ACU_LIMIT", "").strip()
DEVIN_MAX_ACU_LIMIT: int | None = int(_max_acu) if _max_acu.isdigit() else None
