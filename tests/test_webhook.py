import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import app as app_module
import config
from devin_client import CreatedSession


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_WEBHOOK_SECRET", "", raising=False)

    def fake_create_session(self, prompt, **kwargs):
        fake_create_session.last_prompt = prompt
        fake_create_session.last_kwargs = kwargs
        return CreatedSession(
            session_id="devin-123",
            url="https://app.devin.ai/sessions/123",
            is_new_session=True,
        )

    monkeypatch.setattr(app_module.DevinClient, "create_session", fake_create_session)
    app_module._fake_create_session = fake_create_session
    return TestClient(app_module.app)


def _issue_payload(action="opened", labels=("dependency_upgrade",), title="Upgrade requests to 2.32.0", body="Dependency: requests\nVersion: 2.32.0"):
    return {
        "action": action,
        "issue": {
            "number": 7,
            "title": title,
            "body": body,
            "html_url": "https://github.com/your-org/your-repo/issues/7",
            "labels": [{"name": n} for n in labels],
        },
    }


def _post(client, payload, event="issues"):
    return client.post(
        "/webhook",
        content=json.dumps(payload),
        headers={"X-GitHub-Event": event, "Content-Type": "application/json"},
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ping(client):
    r = _post(client, {}, event="ping")
    assert r.json()["status"] == "pong"


def test_triggers_session_on_labeled_issue(client):
    r = _post(client, _issue_payload())
    data = r.json()
    assert r.status_code == 200
    assert data["status"] == "session_created"
    assert data["dependency"] == "requests"
    assert data["target_version"] == "2.32.0"
    assert data["session_url"].endswith("/123")
    # Prompt should ask to identify current version + research changelog.
    prompt = app_module._fake_create_session.last_prompt
    assert "CURRENT version" in prompt
    assert "changelog" in prompt


def test_ignores_issue_without_label(client):
    r = _post(client, _issue_payload(labels=("bug",)))
    assert r.json()["status"] == "ignored"


def test_ignores_non_issue_event(client):
    r = _post(client, _issue_payload(), event="push")
    assert r.json()["status"] == "ignored"


def test_ignores_unhandled_action(client):
    r = _post(client, _issue_payload(action="closed"))
    assert r.json()["status"] == "ignored"


def test_unparseable_dependency_returns_422(client):
    r = _post(client, _issue_payload(title="Please fix things", body="no dependency here"))
    assert r.status_code == 422


def test_signature_verification(monkeypatch):
    secret = "topsecret"
    monkeypatch.setattr(config, "GITHUB_WEBHOOK_SECRET", secret, raising=False)
    monkeypatch.setattr(
        app_module.DevinClient,
        "create_session",
        lambda self, prompt, **kw: CreatedSession("devin-1", "https://app.devin.ai/sessions/1"),
    )
    c = TestClient(app_module.app)
    payload = json.dumps(_issue_payload()).encode()

    # Missing signature -> 401
    r = c.post("/webhook", content=payload, headers={"X-GitHub-Event": "issues"})
    assert r.status_code == 401

    # Valid signature -> 200
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    r = c.post(
        "/webhook",
        content=payload,
        headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": sig},
    )
    assert r.status_code == 200
