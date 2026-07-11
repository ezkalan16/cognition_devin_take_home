# Devin dependency-upgrade webhook

A small FastAPI service that listens for GitHub issue webhooks and, whenever an
issue is raised (or labeled) with the **`dependency_upgrade`** label, triggers a
[Devin](https://devin.ai) session via the Devin API to perform the upgrade.

The issue is expected to contain the **name of the dependency** and the
**version to upgrade to**. The triggered Devin session is instructed to:

1. **Identify the current version** of the dependency used in the code
   repository (by inspecting manifests/lockfiles such as `package.json`,
   `requirements.txt`, `pyproject.toml`, `go.mod`, `Cargo.toml`, etc.).
2. **Research** any changelog, release notes, and upgrade/migration guides
   relevant between the current version and the new version.
3. **Locate every usage** of the dependency in the codebase (imports, calls,
   config) and record each file/line.
4. **Produce a categorized impact report** (`DEPENDENCY_UPGRADE_REPORT.md`) that
   evaluates the researched changes against the actual usages, links each item
   to where it is used in the codebase, and groups them into four categories:
   - **Breaking changes** — must be fixed for the upgrade.
   - **New deprecations** — still work but should be migrated.
   - **Changes to existing functionality** — behavioral changes to used APIs.
   - **New functionality that can be used in the codebase** — newly added
     features relevant to how the codebase uses the dependency.
5. **Perform the upgrade** and open a pull request that includes the impact
   report.
6. **Handle deprecations**: for each deprecated piece of functionality the
   codebase uses, open a **separate PR** replacing it with the recommended
   alternative — or, if that isn't possible, open a **GitHub issue** describing
   the dependency upgrade, the impacted area(s) of the codebase, and the
   deprecated functionality.
7. **Assess behavioral impact**: for each change to existing functionality,
   evaluate whether it affects the codebase's behavior given how it uses that
   functionality; if there is any impact, generate a `BEHAVIORAL_IMPACT_REPORT.md`
   highlighting it for human review.
8. **Surface usable new functionality**: if new functionality could improve the
   codebase, open a **GitHub issue** describing the upgrade, the new
   functionality available, and where in the codebase it could be used.
9. **Keep the original issue updated**: as its first task, comment that the
   upgrade was picked up and include the Devin session ID. Immediately before
   finishing, add a completion comment containing every generated report and
   links to every pull request and issue created during the session.

> The repository URL and Devin API token are **placeholders** — set them via
> environment variables (see `.env.example`).

## How it works

```text
+-----------------------------------+
| GitHub target repository          |
|                                   |
| Issue opened/labeled with:        |
| dependency_upgrade                |
+-----------------+-----------------+
                  |
                  | GitHub "issues" webhook
                  v
+-----------------------------------+
| FastAPI service                   |
|                                   |
| POST /webhook  <-- entrypoint     |
|                                   |
| 1. Verify HMAC signature          |
| 2. Check event, action, and label |
| 3. Parse dependency and version   |
| 4. Build the upgrade prompt       |
| 5. Send session ID to Devin       |
+-----------------+-----------------+
                  |
                  | POST /v1/sessions, then
                  | POST /v1/sessions/{id}/message
                  v
+-----------------------------------+
| Devin session                     |
|                                   |
| 1. Comment issue with session ID  |
| 2. Clone/read the target repo     |
| 3. Find version, usages, impact   |
| 4. Update code and run tests      |
| 5. Open required PRs/issues       |
| 6. Comment reports + all links    |
+-----------------+-----------------+
                  |
                  | All outbound GitHub interaction
                  v
+-----------------------------------+
| GitHub target repository          |
|                                   |
| - Original issue status updates   |
| - Upgrade PR + impact report      |
| - Deprecation PRs or issues       |
| - Behavioral impact report        |
| - New-functionality issues        |
+-----------------------------------+
```

The webhook service does not call the GitHub API or modify the repository directly.
After creating the session, it uses the Devin messaging API to provide the new session
ID. The Devin session performs every outbound GitHub interaction: pickup and
completion comments on the original issue, repository changes, pull requests, and
follow-up issues. The session's GitHub integration therefore needs permission to read
the repository, comment on issues, and create issues and pull requests.

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
