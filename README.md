# Devin dependency-upgrade webhook

A small FastAPI service that listens for GitHub issue webhooks and, whenever an
issue is raised (or labeled) with the **`dependency_upgrade`** label, triggers a
[Devin](https://devin.ai) session via the Devin API to perform the upgrade.

The issue is expected to contain the **name of the dependency** and the
**version to upgrade to**.

## Application workflow

For each request to `POST /webhook`, the FastAPI app performs these steps in
order:

1. Read the raw request body and verify `X-Hub-Signature-256` when a webhook
   secret is configured.
2. Return `pong` for GitHub `ping` events and ignore events other than `issues`.
3. Accept only `opened`, `reopened`, `labeled`, and `edited` issue actions.
4. Require the configured trigger label (default: `dependency_upgrade`).
5. Parse the dependency name and target version, then validate the issue number
   and resolve the original issue URL.
6. Build the dependency-upgrade prompt and session title.
7. Create an idempotent Devin session with `POST /v1/sessions`.
8. Send the resulting session ID, session URL, and pickup-comment instructions
   to that session with `POST /v1/sessions/{session_id}/message`.
9. Return the dependency, target version, session ID, session URL, and
   `issue_update_requested=true` to the webhook caller.

## Devin session workflow

The follow-up message makes the pickup update Devin's first task. The session
then performs the main upgrade prompt in this order:

1. **Comment on the original issue** that the upgrade was picked up and sent to
   Devin, including the Devin session ID and link. Existing marker comments are
   checked first to prevent duplicates.
2. **Identify the current version** from the repository manifests and lockfiles.
3. **Query DeepWiki first** for indexed context about the target repository and,
   when available, the dependency's public source repository. Verify every
   finding against the current checkout and continue without blocking if
   DeepWiki is unavailable or a repository is not indexed.
4. **Research authoritative sources** such as official changelogs, release notes,
   and upgrade/migration guides to confirm or correct the DeepWiki findings.
5. **Locate every usage** of the dependency and record its file and line.
6. **Prepare a categorized Markdown impact report** in session context,
   evaluating researched changes against actual usage under breaking changes,
   new deprecations, changes to existing functionality, and usable new
   functionality. No report file is created in the repository.
7. **Perform the upgrade**, apply required code changes, and run the project
   build and tests.
8. **Open the main upgrade PR** with the versions, migration steps, validation,
   and original issue link, but without report files or report content.
9. **Handle deprecations** with separate replacement PRs, or GitHub issues when
   replacement is not feasible.
10. **Assess behavioral impact** and prepare a Markdown report in session context
    for human review when existing functionality changes affect the codebase.
11. **Surface usable new functionality** in GitHub issues that link to relevant
    codebase locations.
12. **Comment on the original issue before finishing**, placing every report's
    complete Markdown content there and linking every pull request and GitHub
    issue created by the session.

> The repository URL and Devin API token are **placeholders** — set them via
> environment variables (see `.env.example`).

## How it works

```text
+-------------------------------------+
| GitHub target repository            |
| dependency_upgrade issue event      |
+------------------+------------------+
                   | POST /webhook
                   v
+-------------------------------------+
| FastAPI app                         |
|                                     |
| 1. Verify webhook signature         |
| 2. Route event and validate action  |
| 3. Require trigger label            |
| 4. Parse dependency + issue data    |
| 5. Build prompt + session title     |
| 6. POST /v1/sessions                |
| 7. POST /v1/sessions/{id}/message   |
| 8. Return session metadata          |
+------------------+------------------+
                   | Devin APIs only
                   v
+-------------------------------------+
| Devin session                       |
|                                     |
| 1. Comment pickup + session ID      |
| 2. Query DeepWiki, then verify      |
| 3. Research, report, and upgrade    |
| 4. Open required PRs/issues         |
| 5. Comment report content + links   |
+------------------+------------------+
                   | All outbound GitHub actions
                   v
+-------------------------------------+
| GitHub target repository            |
| issue comments (reports), PRs/issues|
+-------------------------------------+
```

The webhook service does not call the GitHub API or modify the repository directly.
After creating the session, it uses the Devin messaging API to provide the new session
ID. The Devin session performs every outbound GitHub interaction: pickup and
completion comments on the original issue, repository changes, pull requests, and
follow-up issues. The session's GitHub integration therefore needs permission to read
the repository, comment on issues, and create issues and pull requests.

DeepWiki is used as an indexed research aid, not as the sole source of truth. The
session verifies its findings against the current checkout and confirms version-specific
changes with official dependency documentation. A missing or stale DeepWiki index does
not block the upgrade.

Reports are never written, staged, or committed as repository files, and their content is
not copied into pull request descriptions or follow-up issues. The original dependency-
upgrade issue's final completion comment is the only GitHub location containing the full
Markdown reports.

## Files

| File                    | Purpose                                                        |
| ----------------------- | -------------------------------------------------------------- |
| `app.py`                | FastAPI app + `/webhook` handler (signature check, filtering). |
| `Dockerfile`            | Production container image for the webhook service.             |
| `package.json`          | Smee relay and end-to-end local webhook test commands.          |
| `config.py`             | Environment-driven configuration (with placeholders).          |
| `dependency_parser.py`  | Extracts `(name, version)` from the issue title/body.          |
| `prompt.py`             | Builds the instruction prompt for the Devin session.           |
| `devin_client.py`       | Client for creating sessions and sending follow-up messages.   |
| `tests/`                | Unit tests plus the Smee end-to-end webhook test.              |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # then edit .env
```

Set the required environment variables (or edit `.env`):

| Variable                | Required | Description                                                   |
| ----------------------- | -------- | ------------------------------------------------------------- |
| `DEVIN_API_KEY`         | yes      | Devin API key (`cog_` prefix).                                |
| `LOG_LEVEL`             | no       | App log level; defaults to `INFO`. Set to `DEBUG` for diagnostics. |
| `TARGET_REPO_URL`       | yes      | Repository the session should upgrade.                        |
| `GITHUB_WEBHOOK_SECRET` | recommended | Shared secret to verify `X-Hub-Signature-256`.             |
| `DEVIN_API_BASE_URL`    | no       | Defaults to `https://api.devin.ai`.                           |
| `TRIGGER_LABEL`         | no       | Defaults to `dependency_upgrade`.                             |
| `DEVIN_MAX_ACU_LIMIT`   | no       | Optional ACU cap for triggered sessions.                      |
| `SMEE_URL`              | local testing | Smee channel that relays GitHub webhooks to localhost.     |

## Run

```bash
uvicorn app:app --reload --port 8000 --env-file .env
```

At the default `LOG_LEVEL=INFO`, the app logs startup configuration, webhook
routing and filtering decisions, parsed upgrade requests, and Devin session
creation and delivery of the session-ID follow-up instruction. Set
`LOG_LEVEL=DEBUG` for additional request metadata such as prompt/message lengths and
API response statuses. Logs omit webhook payload contents, signatures, API keys,
prompt contents, and session-message contents.

### Docker

Build the image and run it with the same environment variables:

```bash
docker build -t devin-dependency-upgrade-webhook .
docker run --rm -p 8000:8000 --env-file .env devin-dependency-upgrade-webhook
```

The service is available on port `8000`; container health checks use `GET /health`.

### Test GitHub webhooks locally with Smee

With Node.js 20.18.1 or newer, create a channel at
[smee.io](https://smee.io/new), set its URL as `SMEE_URL` in `.env`, and use that
same URL as the GitHub webhook **Payload URL**. Then install and start the Smee
client alongside the local app:

```bash
npm install
npm run smee
```

The relay forwards channel events to `http://127.0.0.1:8000/webhook` by default.
Set `SMEE_TARGET_URL` to override the local target.

To test the complete relay without creating a real Devin session, stop any manual
relay using the same channel and run:

```bash
npm run test:smee
```

The test starts the FastAPI app and a mock Devin API, posts a signed GitHub issue
event to `SMEE_URL`, and verifies that Smee forwards it through the app into both
the session-creation request and the follow-up message containing the session ID.

## Configure the GitHub webhook

In your repository: **Settings → Webhooks → Add webhook**

- **Payload URL:** `https://<your-host>/webhook`
- **Content type:** `application/json`
- **Secret:** the same value as `GITHUB_WEBHOOK_SECRET`
- **Events:** *Let me select individual events* → **Issues**

## Example triggering issue

```
Title: Upgrade requests to 2.32.0

Dependency: requests
Version: 2.32.0
```

Other phrasings also work, e.g. `requests==2.32.0` or
"bump lodash to v4.17.21".

## Tests

```bash
pip install pytest
pytest -q
```
