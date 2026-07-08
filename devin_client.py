"""Minimal client for the Devin REST API."""
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class CreatedSession:
    session_id: str
    url: str
    is_new_session: bool | None = None


class DevinClient:
    """Thin wrapper around the Devin `POST /v1/sessions` endpoint."""

    def __init__(self, api_key: str, base_url: str = "https://api.devin.ai", timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def create_session(
        self,
        prompt: str,
        *,
        title: str | None = None,
        idempotent: bool = True,
        max_acu_limit: int | None = None,
        tags: list[str] | None = None,
    ) -> CreatedSession:
        """Create a new Devin session and return its id/url.

        Raises httpx.HTTPStatusError on a non-2xx response.
        """
        payload: dict[str, object] = {"prompt": prompt, "idempotent": idempotent}
        if title is not None:
            payload["title"] = title
        if max_acu_limit is not None:
            payload["max_acu_limit"] = max_acu_limit
        if tags:
            payload["tags"] = tags

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._base_url}/v1/sessions",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return CreatedSession(
            session_id=data["session_id"],
            url=data["url"],
            is_new_session=data.get("is_new_session"),
        )
