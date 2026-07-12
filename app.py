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
import json
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

import config
from dependency_parser import parse_dependency
from devin_client import DevinClient
from prompt import build_session_started_message, build_upgrade_prompt

_log_level = logging.getLevelNamesMapping().get(config.LOG_LEVEL, logging.INFO)
logging.basicConfig(level=_log_level)
logger = logging.getLogger("dependency-upgrade-webhook")
logger.setLevel(_log_level)

app = FastAPI(title="Devin Dependency-Upgrade Webhook")
logger.info(
    "Application configured target_repo=%s trigger_label=%s signature_verification=%s",
    config.TARGET_REPO_URL,
    config.TRIGGER_LABEL,
    bool(config.GITHUB_WEBHOOK_SECRET),
)
logger.debug(
    "Devin request configuration api_base_url=%s max_acu_limit=%s",
    config.DEVIN_API_BASE_URL,
    config.DEVIN_MAX_ACU_LIMIT,
)


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
    return DevinClient(api_key=config.DEVIN_API_KEY, org_id=config.DEVIN_ORG_ID,base_url=config.DEVIN_API_BASE_URL)


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
    logger.info("Received webhook event=%r", x_github_event)
    logger.debug(
        "Webhook metadata body_bytes=%d signature_required=%s signature_present=%s",
        len(raw_body),
        bool(config.GITHUB_WEBHOOK_SECRET),
        bool(x_hub_signature_256),
    )

    if not _verify_signature(config.GITHUB_WEBHOOK_SECRET, raw_body, x_hub_signature_256):
        logger.warning("Rejected webhook event=%r: invalid signature", x_github_event)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event == "ping":
        logger.info("Responding to GitHub ping event")
        return {"status": "pong"}

    if x_github_event != "issues":
        logger.info("Ignoring unsupported webhook event=%r", x_github_event)
        return {"status": "ignored", "reason": f"event '{x_github_event}' is not an issue event"}

    payload = await request.json()
    if payload_json := json.loads(payload.get("payload")):
        payload = payload_json
    action = payload.get("action")
    logger.info("Processing issue webhook action=%r", action)
    # React when an issue is opened, reopened, or the label is added.
    if action not in {"opened", "reopened", "labeled", "edited"}:
        logger.info("Ignoring issue webhook action=%r: unsupported action", action)
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    issue = payload.get("issue") or {}
    issue_number = issue.get("number")
    if not _has_trigger_label(issue, config.TRIGGER_LABEL):
        logger.info(
            "Ignoring issue webhook issue_number=%s action=%s: missing trigger_label=%s",
            issue_number,
            action,
            config.TRIGGER_LABEL,
        )
        return {"status": "ignored", "reason": f"missing '{config.TRIGGER_LABEL}' label"}
    logger.debug(
        "Matched trigger label issue_number=%s action=%s trigger_label=%s",
        issue_number,
        action,
        config.TRIGGER_LABEL,
    )

    title = issue.get("title")
    body = issue.get("body")
    parsed = parse_dependency(title, body)
    logger.info(
        "Parsed dependency request issue_number=%s dependency=%r target_version=%r",
        issue_number,
        parsed.name,
        parsed.version,
    )

    if not parsed.name:
        logger.warning("Could not parse dependency from issue_number=%s", issue_number)
        raise HTTPException(
            status_code=422,
            detail="Could not determine the dependency name from the issue.",
        )
    if not isinstance(issue_number, int):
        raise HTTPException(status_code=422, detail="GitHub issue number is missing")

    issue_url = issue.get("html_url") or (
        f"{config.TARGET_REPO_URL.rstrip('/')}/issues/{issue_number}"
    )
    prompt = build_upgrade_prompt(
        repo_url=config.TARGET_REPO_URL,
        dependency=parsed.name,
        target_version=parsed.version or "",
        issue_number=issue_number,
        issue_url=issue_url,
        issue_title=title,
        issue_body=body,
    )

    session_title = f"Upgrade {parsed.name} to {parsed.version or 'latest'}"
    logger.debug(
        "Built Devin session request issue_number=%s title=%r prompt_chars=%d "
        "max_acu_limit=%s",
        issue_number,
        session_title,
        len(prompt),
        config.DEVIN_MAX_ACU_LIMIT,
    )
    logger.info(
        "Requesting Devin session issue_number=%s dependency=%s target_version=%s",
        issue_number,
        parsed.name,
        parsed.version or "latest",
    )
    devin_client = _get_client()
    try:
        session = devin_client.create_session(
            prompt,
            title=session_title,
            idempotent=True,
            max_acu_limit=config.DEVIN_MAX_ACU_LIMIT,
            tags=["dependency-upgrade"],
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Devin API request failed status=%s dependency=%s target_version=%s",
            exc.response.status_code,
            parsed.name,
            parsed.version,
        )
        raise HTTPException(status_code=502, detail="Failed to create Devin session") from exc

    logger.info(
        "Created Devin session session_id=%s dependency=%s target_version=%s session_url=%s",
        session.session_id,
        parsed.name,
        parsed.version,
        session.url,
    )

    started_message = build_session_started_message(
        issue_url=issue_url,
        session_id=session.session_id,
        session_url=session.url,
        dependency=parsed.name,
        target_version=parsed.version,
    )
    try:
        devin_client.send_message(session.session_id, started_message)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Failed to send GitHub pickup instructions to Devin status=%s "
            "issue_number=%s session_id=%s",
            exc.response.status_code,
            issue_number,
            session.session_id,
        )
        raise HTTPException(
            status_code=502,
            detail="Devin session created but issue-update instructions failed",
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "Failed to send GitHub pickup instructions to Devin "
            "issue_number=%s session_id=%s",
            issue_number,
            session.session_id,
        )
        raise HTTPException(
            status_code=502,
            detail="Devin session created but issue-update instructions failed",
        ) from exc

    logger.info(
        "Sent GitHub pickup instructions to Devin issue_number=%s session_id=%s",
        issue_number,
        session.session_id,
    )

    return {
        "status": "session_created",
        "dependency": parsed.name,
        "target_version": parsed.version,
        "session_id": session.session_id,
        "session_url": session.url,
        "issue_update_requested": True,
    }
