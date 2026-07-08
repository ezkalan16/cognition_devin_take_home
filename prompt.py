"""Builds the prompt sent to a Devin session for a dependency upgrade."""
from __future__ import annotations

# The impact categories the generated report must use. Each entry is
# (heading, guidance shown to the session).
IMPACT_CATEGORIES: list[tuple[str, str]] = [
    (
        "Breaking changes",
        "changes that will break the codebase as currently written and MUST be "
        "fixed for the upgrade (removed/renamed APIs, changed signatures or "
        "return types, changed default behavior).",
    ),
    (
        "New deprecations",
        "APIs the codebase uses that still work on the target version but are now "
        "deprecated and should be migrated soon.",
    ),
    (
        "Changes to existing functionality",
        "behavioral changes to APIs the codebase uses that are not strictly "
        "breaking but may alter results, performance, or edge cases.",
    ),
    (
        "New functionality that can be used in the codebase",
        "new features/APIs introduced up to the target version that are relevant "
        "to how this codebase uses the dependency and could simplify or improve it.",
    ),
]


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
      3. Locate every usage of the dependency in the codebase.
      4. Evaluate the researched changes against those usages and produce a
         categorized impact report (breaking changes, new deprecations, changes
         to existing functionality, new functionality) linking to each usage.
      5. Perform the upgrade and open a PR that includes the report.
      6. For each deprecation, open a PR replacing the deprecated usage, or —
         if that is not possible — open a GitHub issue describing the upgrade,
         impacted areas, and the deprecated functionality.
      7. For changes to existing functionality, assess behavioral impact on the
         codebase and, if any, generate a report for human review.
    """
    target = target_version.strip() or "the latest version"

    category_lines: list[str] = []
    for heading, guidance in IMPACT_CATEGORIES:
        category_lines.append(f"   - **{heading}**: {guidance}")

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
        f"`{target}`. Compile the full set of relevant changes (breaking "
        "changes, deprecations, behavioral changes, and newly added features).",
        "",
        f"3. Find EVERY usage of `{dependency}` in the codebase: imports, "
        "function/class/method calls, configuration, and any indirect usage. "
        "Record the exact file path and line number for each usage so it can be "
        "referenced.",
        "",
        "4. Evaluate the changes from step 2 against the actual usages from "
        f"step 3 and produce an IMPACT REPORT. Only include changes that are "
        "relevant to how this codebase uses the dependency. Categorize every "
        "relevant change under one of the following headings:",
        "",
        *category_lines,
        "",
        "   For each item in the report: give a one-line description of the "
        "change, cite the specific changelog/release-note source, and link to "
        "the exact place(s) in the codebase it affects using permalinks of the "
        f"form {repo_url}/blob/<commit-sha>/<path>#L<line> (or `path:line` if a "
        "commit permalink is not available). If a category has no relevant "
        "items, state \"None\" under that heading. Write the report to "
        "`DEPENDENCY_UPGRADE_REPORT.md` at the repo root.",
        "",
        f"5. Perform the upgrade: bump `{dependency}` to `{target}` in the "
        "appropriate manifest(s) and lockfile(s), then apply the code changes "
        "required by the breaking changes and deprecations you identified so "
        "the project builds and its tests pass.",
        "",
        "6. Open a pull request with the upgrade. Include the full impact report "
        "(the four categories with codebase links) in the PR description, along "
        "with the current version, the target version, and the migration steps "
        "you applied.",
        "",
        "7. Handle the deprecations from the \"New deprecations\" category. For "
        "each deprecated piece of functionality the codebase uses:",
        "",
        "   - If it is possible to migrate off it, open a SEPARATE pull request "
        "that replaces the usage of the deprecated functionality with the "
        "recommended non-deprecated alternative.",
        "   - If replacing it is NOT possible (e.g. no drop-in replacement "
        "exists, or the migration is too large/risky to do automatically), open "
        f"a GitHub issue in {repo_url} instead. The issue MUST describe: the "
        f"dependency upgrade (`{dependency}` from the current version to "
        f"`{target}`), the area(s) of the codebase that are impacted (with links "
        "to the usage sites), and the specific deprecated functionality that "
        "needs to be addressed.",
        "",
        "   If there are no deprecations, skip this step.",
        "",
        "8. Assess the \"Changes to existing functionality\" category for "
        "behavioral impact. For each such change, determine whether it would "
        "actually affect the behavior of THIS codebase given how it uses the "
        "affected functionality (consider the arguments passed, the return "
        "values relied on, and the surrounding logic at each usage site). If "
        "any change would impact the codebase's behavior, generate a "
        "`BEHAVIORAL_IMPACT_REPORT.md` for HUMAN REVIEW that, for each impacted "
        "usage, describes the behavioral change, links to the affected code "
        f"({repo_url}/blob/<commit-sha>/<path>#L<line>), and explains the likely "
        "effect on the codebase. If no change has any behavioral impact, state "
        "that explicitly instead of creating the report.",
    ]

    if issue_number is not None or issue_url:
        ref = issue_url or f"#{issue_number}"
        lines += ["", f"This upgrade was requested via GitHub issue {ref}."]

    if issue_title:
        lines += ["", f"Issue title: {issue_title}"]
    if issue_body:
        lines += [f"Issue body:\n{issue_body.strip()}"]

    return "\n".join(lines)
