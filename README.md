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

> The repository URL and Devin API token are **placeholders** — set them via
> environment variables (see `.env.example`).

## How it works

```
GitHub issue (label: dependency_upgrade)
        │  webhook (event: issues)
        ▼
POST /webhook  ──►  verify HMAC signature
                    check for the trigger label
                    parse dependency name + target version
                    build the upgrade prompt
                    POST /v1/sessions  ──►  Devin
```

## Files

| File                    | Purpose                                                        |
| ----------------------- | -------------------------------------------------------------- |
| `app.py`                | FastAPI app + `/webhook` handler (signature check, filtering). |
| `config.py`             | Environment-driven configuration (with placeholders).          |
| `dependency_parser.py`  | Extracts `(name, version)` from the issue title/body.          |
| `prompt.py`             | Builds the instruction prompt for the Devin session.           |
| `devin_client.py`       | Minimal client for `POST /v1/sessions`.                        |
| `tests/`                | Unit tests for parsing, prompt building, and the webhook.      |

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
| `TARGET_REPO_URL`       | yes      | Repository the session should upgrade.                        |
| `GITHUB_WEBHOOK_SECRET` | recommended | Shared secret to verify `X-Hub-Signature-256`.             |
| `DEVIN_API_BASE_URL`    | no       | Defaults to `https://api.devin.ai`.                           |
| `TRIGGER_LABEL`         | no       | Defaults to `dependency_upgrade`.                             |
| `DEVIN_MAX_ACU_LIMIT`   | no       | Optional ACU cap for triggered sessions.                      |

## Run

```bash
uvicorn app:app --reload --port 8000
```

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
