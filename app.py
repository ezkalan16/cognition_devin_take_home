"""FastAPI webhook service that triggers a Devin session when a GitHub issue
is raised (or labeled) with the `dependency_upgrade` label.

Flow:
  GitHub issue webhook  ->  verify signature  ->  check label
    ->  parse dependency name + target version from the issue
    ->  create a Devin session instructing it to:
          1. identify the current version in the repo,
          2. research changelog / release notes / upgrade guides,
          3. perform the upgrade and open a PR.

Run locally:
    uvicorn app:app --reload --port 8000
"""
from __future__ import annotations

import hashlib
import hmac
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

import config
from dependency_parser import parse_dependency
from devin_client import DevinClient
from prompt import build_upgrade_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dependency-upgrade-webhook")

app = FastAPI(title="Devin Dependency-Upgrade Webhook")


def _verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify GitHub's X-Hub-Signature-256 HMAC-SHA256 header."""
    if not secret:
        # No secret configured -> verification disabled.
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _has_trigger_label(issue: dict, label: str) -> bool:
    labels = issue.get("labels") or []
    names = {
        (lbl.get("name") if isinstance(lbl, dict) else str(lbl)).lower()
        for lbl in labels
    }
    return label.lower() in names


def _get_client() -> DevinClient:
    return DevinClient(api_key=config.DEVIN_API_KEY, base_url=config.DEVIN_API_BASE_URL)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()

    if not _verify_signature(config.GITHUB_WEBHOOK_SECRET, raw_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event != "issues":
        return {"status": "ignored", "reason": f"event '{x_github_event}' is not an issue event"}

    payload = await request.json()
    action = payload.get("action")
    # React when an issue is opened, reopened, or the label is added.
    if action not in {"opened", "reopened", "labeled", "edited"}:
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    issue = payload.get("issue") or {}
    if not _has_trigger_label(issue, config.TRIGGER_LABEL):
        return {"status": "ignored", "reason": f"missing '{config.TRIGGER_LABEL}' label"}

    title = issue.get("title")
    body = issue.get("body")
    parsed = parse_dependency(title, body)

    if not parsed.name:
        logger.warning("Could not parse a dependency name from issue: %s", title)
        raise HTTPException(
            status_code=422,
            detail="Could not determine the dependency name from the issue.",
        )

    prompt = build_upgrade_prompt(
        repo_url=config.TARGET_REPO_URL,
        dependency=parsed.name,
        target_version=parsed.version or "",
        issue_number=issue.get("number"),
        issue_url=issue.get("html_url"),
        issue_title=title,
        issue_body=body,
    )

    session_title = f"Upgrade {parsed.name} to {parsed.version or 'latest'}"
    try:
        session = _get_client().create_session(
            prompt,
            title=session_title,
            idempotent=True,
            max_acu_limit=config.DEVIN_MAX_ACU_LIMIT,
            tags=["dependency-upgrade"],
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Devin API error: %s - %s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail="Failed to create Devin session") from exc

    logger.info(
        "Created Devin session %s for %s -> %s (%s)",
        session.session_id, parsed.name, parsed.version, session.url,
    )
    return {
        "status": "session_created",
        "dependency": parsed.name,
        "target_version": parsed.version,
        "session_id": session.session_id,
        "session_url": session.url,
    }
