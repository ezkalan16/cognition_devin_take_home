"""Builds the prompt sent to a Devin session for a dependency upgrade."""
from __future__ import annotations


def build_upgrade_prompt(
    *,
    repo_url: str,
    dependency: str,
    target_version: str,
    issue_number: int | None = None,
    issue_url: str | None = None,
    issue_title: str | None = None,
    issue_body: str | None = None,
) -> str:
    """Construct the instruction prompt for the Devin session.

    The prompt asks Devin to:
      1. Identify the dependency's current version in the target repo.
      2. Research changelog / release notes / upgrade guides between the
         current and target versions.
      3. Perform the upgrade and open a PR.
    """
    target = target_version.strip() or "the latest version"
    lines: list[str] = [
        f"Upgrade the dependency `{dependency}` to version `{target}` in the "
        f"repository {repo_url}.",
        "",
        "Steps to follow:",
        "",
        f"1. Identify the CURRENT version of `{dependency}` used in the code "
        "repository. Inspect the relevant dependency manifests and lockfiles "
        "(e.g. package.json / package-lock.json / yarn.lock, "
        "requirements.txt / pyproject.toml / poetry.lock, go.mod / go.sum, "
        "Gemfile.lock, pom.xml, build.gradle, Cargo.toml, etc.) to determine "
        "exactly which version is currently pinned or resolved.",
        "",
        f"2. Research any changelog, release notes, and upgrade/migration "
        f"guides relevant to `{dependency}` between the current version and "
        f"`{target}`. Summarize the breaking changes, deprecations, and "
        "required code migrations that apply to how this repository uses the "
        "dependency.",
        "",
        f"3. Perform the upgrade: bump `{dependency}` to `{target}` in the "
        "appropriate manifest(s) and lockfile(s), then apply any code changes "
        "required by the breaking changes you identified so the project "
        "builds and its tests pass.",
        "",
        "4. Open a pull request with the upgrade. In the PR description, "
        "include the current version, the target version, and a summary of "
        "the relevant changelog/release-note findings and any migration steps "
        "you applied.",
    ]

    if issue_number is not None or issue_url:
        ref = issue_url or f"#{issue_number}"
        lines += ["", f"This upgrade was requested via GitHub issue {ref}."]

    if issue_title:
        lines += ["", f"Issue title: {issue_title}"]
    if issue_body:
        lines += [f"Issue body:\n{issue_body.strip()}"]

    return "\n".join(lines)
