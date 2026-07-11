---
name: testing-smee-webhook-relay
description: Test GitHub webhook delivery through a real Smee channel into the local FastAPI service and mock Devin API.
---

# Testing the Smee webhook relay

## Devin Secrets Needed

None. `SMEE_URL` is local test configuration in the ignored `.env` file. A disposable channel can be created from `https://smee.io/new`.

## Setup

1. Install Python dependencies in `.venv` and run `npm install` for `smee-client`.
2. Copy `.env.example` to `.env` if needed.
3. Set `SMEE_URL` to a dedicated Smee channel. Do not commit `.env`.

## End-to-end test

Run:

```bash
npm run test:smee
```

The command starts the real FastAPI application on a dynamic local port, starts a mock Devin API, subscribes a Smee client to `SMEE_URL`, and posts a signed GitHub-compatible issue event to the channel.

Verify both explicit `PASS` lines, a Smee `POST .../webhook - 200` line, and process exit status 0. The test must capture the expected `/v1/sessions` request; this proves the relayed webhook passed HMAC validation and traversed the application.

Use compact `JSON.stringify` request bytes when signing test payloads because Smee serializes the event body before forwarding. The signature must be computed over exactly those bytes.

## Manual GitHub delivery

Run the application with `.env`, then run `npm run smee`. Configure the GitHub webhook Payload URL to the same `SMEE_URL` and select Issues events. The default local target is `http://127.0.0.1:8000/webhook`; override it with `SMEE_TARGET_URL` when needed.
