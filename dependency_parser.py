"""Extracts the dependency name and target version from a GitHub issue.

The issue is expected to name the dependency and the version to upgrade to.
Because issue authors phrase things differently, several strategies are tried
in order:

  1. Structured "key: value" lines in the body, e.g.
        Dependency: requests
        Version: 2.32.0
  2. A "name@version" / "name==version" token, e.g. "requests==2.32.0".
  3. Natural language, e.g. "Upgrade requests to 2.32.0" or
     "bump lodash to v4.17.21".

Returns a ParsedDependency (name may be present without a version).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedDependency:
    name: str | None
    version: str | None

    @property
    def is_complete(self) -> bool:
        return bool(self.name and self.version)


_VERSION = r"v?\d+(?:\.\d+)*(?:[-.][0-9A-Za-z.]+)?"

# "Dependency: <name>" style keys.
_NAME_KEYS = ("dependency", "package", "library", "name", "module")
_VERSION_KEYS = ("version", "target version", "to version", "new version", "upgrade to")


def _clean_version(v: str) -> str:
    return v.strip().lstrip("vV").strip("`'\" ")


def _clean_name(n: str) -> str:
    return n.strip().strip("`'\" ")


def _parse_structured(text: str) -> ParsedDependency:
    name: str | None = None
    version: str | None = None
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip().lower().lstrip("-*# ").strip()
        value = value.strip()
        if not value:
            continue
        if name is None and key in _NAME_KEYS:
            name = _clean_name(value)
        elif version is None and key in _VERSION_KEYS:
            m = re.search(_VERSION, value)
            if m:
                version = _clean_version(m.group(0))
    return ParsedDependency(name, version)


def _parse_at_token(text: str) -> ParsedDependency:
    # name@1.2.3  or  name==1.2.3  or  name@^1.2.3
    m = re.search(
        rf"(?P<name>[A-Za-z0-9._/@-]+?)\s*(?:@|==)\s*\^?~?(?P<version>{_VERSION})",
        text,
    )
    if m:
        return ParsedDependency(_clean_name(m.group("name")), _clean_version(m.group("version")))
    return ParsedDependency(None, None)


def _parse_natural(text: str) -> ParsedDependency:
    # "upgrade/bump/update <name> to [version] <x.y.z>"
    m = re.search(
        rf"(?:upgrade|bump|update|migrate)\s+(?:the\s+)?"
        rf"(?:dependency\s+)?[`'\"]?(?P<name>[A-Za-z0-9._/@-]+)[`'\"]?"
        rf"\s+(?:to|->|=>)\s+(?:version\s+)?[`'\"]?(?P<version>{_VERSION})",
        text,
        re.IGNORECASE,
    )
    if m:
        return ParsedDependency(_clean_name(m.group("name")), _clean_version(m.group("version")))
    return ParsedDependency(None, None)


def parse_dependency(title: str | None, body: str | None) -> ParsedDependency:
    """Best-effort extraction of (name, version) from an issue title/body."""
    title = title or ""
    body = body or ""

    # Structured body fields are the most reliable signal.
    structured = _parse_structured(body)
    if structured.is_complete:
        return structured

    combined = f"{title}\n{body}"
    for strategy in (_parse_at_token, _parse_natural):
        parsed = strategy(combined)
        if parsed.is_complete:
            return parsed

    # Merge whatever partial info we gathered.
    name = structured.name
    version = structured.version
    for parsed in (_parse_at_token(combined), _parse_natural(combined)):
        name = name or parsed.name
        version = version or parsed.version
    return ParsedDependency(name, version)
