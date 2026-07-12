import hashlib
import hmac
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

import app as app_module
import config
from devin_client import CreatedSession, DevinClient


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

    def fake_send_message(self, session_id, message):
        fake_send_message.last_session_id = session_id
        fake_send_message.last_message = message

    monkeypatch.setattr(app_module.DevinClient, "create_session", fake_create_session)
    monkeypatch.setattr(app_module.DevinClient, "send_message", fake_send_message)
    app_module._fake_create_session = fake_create_session
    app_module._fake_send_message = fake_send_message
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
    assert data["issue_update_requested"] is True
    assert app_module._fake_send_message.last_session_id == "devin-123"
    started_message = app_module._fake_send_message.last_message
    assert "FIRST task" in started_message
    assert "picked up and sent to Devin" in started_message
    assert "Devin session ID: `devin-123`" in started_message
    assert "https://app.devin.ai/sessions/123" in started_message
    assert "https://github.com/your-org/your-repo/issues/7" in started_message
    assert "webhook service does not have or use GitHub API credentials" in started_message
    # Prompt should ask to identify current version + research changelog.
    prompt = app_module._fake_create_session.last_prompt
    assert "CURRENT version" in prompt
    assert "changelog" in prompt


def test_info_logs_webhook_lifecycle_without_sensitive_payload(client, caplog):
    caplog.set_level(logging.INFO, logger="dependency-upgrade-webhook")
    sensitive_marker = "private-info-log-details"

    response = _post(
        client,
        _issue_payload(body=f"Dependency: requests\nVersion: 2.32.0\n{sensitive_marker}"),
    )

    assert response.status_code == 200
    assert "Received webhook event='issues'" in caplog.text
    assert "Processing issue webhook action='opened'" in caplog.text
    assert "Parsed dependency request issue_number=7 dependency='requests'" in caplog.text
    assert "Requesting Devin session issue_number=7 dependency=requests" in caplog.text
    assert "Created Devin session session_id=devin-123 dependency=requests" in caplog.text
    assert "Sent GitHub pickup instructions to Devin issue_number=7" in caplog.text
    assert "Built Devin session request" not in caplog.text
    assert sensitive_marker not in caplog.text


def test_info_logs_ignored_webhook_reasons(client, caplog):
    caplog.set_level(logging.INFO, logger="dependency-upgrade-webhook")

    _post(client, _issue_payload(), event="push")
    _post(client, _issue_payload(action="closed"))
    _post(client, _issue_payload(labels=("bug",)))

    assert "Ignoring unsupported webhook event='push'" in caplog.text
    assert "Ignoring issue webhook action='closed': unsupported action" in caplog.text
    assert "missing trigger_label=dependency_upgrade" in caplog.text


def test_debug_logs_webhook_flow_without_sensitive_payload(client, caplog):
    caplog.set_level(logging.DEBUG, logger="dependency-upgrade-webhook")
    sensitive_marker = "private-issue-details"

    response = _post(
        client,
        _issue_payload(body=f"Dependency: requests\nVersion: 2.32.0\n{sensitive_marker}"),
    )

    assert response.status_code == 200
    assert "Received webhook event='issues'" in caplog.text
    assert "Matched trigger label issue_number=7" in caplog.text
    assert "Parsed dependency request issue_number=7 dependency='requests'" in caplog.text
    assert "Built Devin session request issue_number=7" in caplog.text
    assert sensitive_marker not in caplog.text


def test_devin_client_debug_logs_metadata_without_secrets(monkeypatch, caplog):
    api_key = "cog_private_api_key"
    prompt = "private Devin prompt"
    response_marker = "private Devin response"

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "session_id": "devin-123",
                "url": "https://app.devin.ai/sessions/123",
                "is_new_session": True,
                "debug": response_marker,
            }

    class FakeHttpClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def post(self, endpoint, *, headers, json):
            assert headers["Authorization"] == f"Bearer {api_key}"
            assert json["prompt"] == prompt
            return FakeResponse()

    monkeypatch.setattr("devin_client.httpx.Client", FakeHttpClient)
    caplog.set_level(logging.DEBUG, logger="dependency-upgrade-webhook.devin-client")

    DevinClient(api_key=api_key).create_session(
        prompt,
        title="Upgrade requests",
        max_acu_limit=5,
        tags=["dependency-upgrade"],
    )

    assert "Creating Devin session endpoint=https://api.devin.ai/v1/sessions" in caplog.text
    assert "title='Upgrade requests'" in caplog.text
    assert "prompt_chars=20" in caplog.text
    assert "Devin API response status=200" in caplog.text
    assert api_key not in caplog.text
    assert prompt not in caplog.text
    assert response_marker not in caplog.text


def test_devin_client_sends_message_without_logging_secrets(monkeypatch, caplog):
    api_key = "cog_private_api_key"
    message = "private session instructions"

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeHttpClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def post(self, endpoint, *, headers, json):
            assert endpoint == "https://api.devin.ai/v1/sessions/devin-123/message"
            assert headers["Authorization"] == f"Bearer {api_key}"
            assert json == {"message": message}
            return FakeResponse()

    monkeypatch.setattr("devin_client.httpx.Client", FakeHttpClient)
    caplog.set_level(logging.DEBUG, logger="dependency-upgrade-webhook.devin-client")

    DevinClient(api_key=api_key).send_message("devin-123", message)

    assert "message_chars=28" in caplog.text
    assert "Devin message response status=200" in caplog.text
    assert api_key not in caplog.text
    assert message not in caplog.text


def test_devin_api_error_does_not_log_response_body(client, monkeypatch, caplog):
    response_marker = "private Devin error response"
    response = httpx.Response(
        500,
        request=httpx.Request("POST", "https://api.devin.ai/v1/sessions"),
        text=response_marker,
    )

    def fail_create_session(self, prompt, **kwargs):
        raise httpx.HTTPStatusError("failure", request=response.request, response=response)

    monkeypatch.setattr(app_module.DevinClient, "create_session", fail_create_session)
    caplog.set_level(logging.DEBUG, logger="dependency-upgrade-webhook")

    result = _post(client, _issue_payload())

    assert result.status_code == 502
    assert "Devin API request failed status=500" in caplog.text
    assert response_marker not in caplog.text


def test_session_message_error_does_not_log_response_body(client, monkeypatch, caplog):
    response_marker = "private Devin message error response"
    response = httpx.Response(
        500,
        request=httpx.Request(
            "POST",
            "https://api.devin.ai/v1/sessions/devin-123/message",
        ),
        text=response_marker,
    )

    def fail_send_message(self, session_id, message):
        raise httpx.HTTPStatusError(
            "failure",
            request=response.request,
            response=response,
        )

    monkeypatch.setattr(app_module.DevinClient, "send_message", fail_send_message)
    caplog.set_level(logging.DEBUG, logger="dependency-upgrade-webhook")

    result = _post(client, _issue_payload())

    assert result.status_code == 502
    assert result.json()["detail"] == (
        "Devin session created but issue-update instructions failed"
    )
    assert "Failed to send GitHub pickup instructions to Devin status=500" in caplog.text
    assert response_marker not in caplog.text


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


def test_signature_verification(monkeypatch, caplog):
    secret = "topsecret"
    caplog.set_level(logging.DEBUG, logger="dependency-upgrade-webhook")
    monkeypatch.setattr(config, "GITHUB_WEBHOOK_SECRET", secret, raising=False)
    monkeypatch.setattr(
        app_module.DevinClient,
        "create_session",
        lambda self, prompt, **kw: CreatedSession("devin-1", "https://app.devin.ai/sessions/1"),
    )
    monkeypatch.setattr(app_module.DevinClient, "send_message", lambda self, session_id, message: None)
    c = TestClient(app_module.app)
    payload = json.dumps(_issue_payload()).encode()

    # Missing signature -> 401
    r = c.post("/webhook", content=payload, headers={"X-GitHub-Event": "issues"})
    assert r.status_code == 401
    assert "Rejected webhook event='issues': invalid signature" in caplog.text
    assert secret not in caplog.text

    # Valid signature -> 200
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    r = c.post(
        "/webhook",
        content=payload,
        headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": sig},
    )
    assert r.status_code == 200
