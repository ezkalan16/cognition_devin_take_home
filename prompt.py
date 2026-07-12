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


def build_session_started_message(
    *,
    issue_url: str,
    session_id: str,
    session_url: str,
    dependency: str,
    target_version: str | None,
) -> str:
    """Build the first follow-up instruction sent after session creation."""
    pickup_marker = f"<!-- devin-dependency-upgrade-session:{session_id} -->"
    completion_marker = f"<!-- devin-dependency-upgrade-complete:{session_id} -->"
    target = target_version or "latest"
    return "\n".join(
        [
            "Your Devin session has started. As your FIRST task, use the GitHub "
            "access available inside this Devin session to update the original "
            f"dependency-upgrade issue: {issue_url}",
            "",
            "Read the existing issue comments first. If the following marker is "
            "already present, do not add a duplicate pickup comment:",
            pickup_marker,
            "",
            "Otherwise, post a comment that includes the marker and says that "
            "the dependency upgrade has been picked up and sent to Devin. The "
            "comment must include:",
            f"- Devin session ID: `{session_id}`",
            f"- Devin session link: {session_url}",
            f"- Dependency: `{dependency}`",
            f"- Target version: `{target}`",
            "",
            "Perform this GitHub interaction yourself; the webhook service does "
            "not have or use GitHub API credentials. After posting the pickup "
            "comment, continue with the dependency-upgrade instructions.",
            "",
            "When you later post the final completion comment required by the "
            "main prompt, include this marker so retries can be detected:",
            completion_marker,
        ]
    )


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
      2. Consult DeepWiki for repository and dependency context, then verify its
         findings against the current checkout.
      3. Research official changelog / release notes / upgrade guides between
         the current and target versions.
      4. Locate every usage of the dependency in the codebase.
      5. Evaluate the researched changes against those usages and prepare a
         categorized Markdown impact report for the original issue comment.
      6. Perform the upgrade.
      7. Open the main upgrade PR without creating or committing report files.
      8. For each deprecation, open a PR replacing the deprecated usage, or —
         if that is not possible — open a GitHub issue describing the upgrade,
         impacted areas, and the deprecated functionality.
      9. For changes to existing functionality, assess behavioral impact on the
         codebase and, if any, prepare Markdown for the original issue comment.
      10. For new functionality, open a GitHub issue describing the upgrade, the
          new functionality, and where it could improve the codebase.
      11. Before finishing, update the original request issue with all generated
          reports and links to every pull request and issue created.
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
        "2. Use Devin's DeepWiki functionality as the FIRST research source. "
        f"Query DeepWiki for the target repository and, when available, the "
        f"public source repository for `{dependency}`. Use it to understand "
        "the codebase architecture, likely dependency integration points, and "
        "relevant dependency APIs or changes. Treat DeepWiki as reusable "
        "indexed context, not as the sole source of truth. Verify every finding "
        "against the CURRENT checkout and exact commit because the index may "
        "lag the branch. If DeepWiki is unavailable or a repository is not "
        "indexed, record that limitation and continue without blocking the "
        "upgrade.",
        "",
        f"3. Research the official changelog, release notes, and "
        f"upgrade/migration guides relevant to `{dependency}` between the "
        f"current version and `{target}`. Use these official sources to confirm "
        "or correct the DeepWiki findings and compile the full set of relevant "
        "changes (breaking changes, deprecations, behavioral changes, and newly "
        "added features).",
        "",
        f"4. Find EVERY usage of `{dependency}` in the codebase: imports, "
        "function/class/method calls, configuration, and any indirect usage. "
        "Use DeepWiki findings to guide the search, but verify the exact file "
        "path and line number for each usage in the current checkout so it can "
        "be referenced.",
        "",
        "5. Evaluate the changes from step 3 against the actual usages from "
        f"step 4 and produce an IMPACT REPORT. Only include changes that are "
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
        "items, state \"None\" under that heading. Keep the complete report "
        "Markdown in the session context for the final comment on the original "
        "GitHub issue. Do NOT create, write, stage, or commit a report file, and "
        "do not copy the report content into a pull request or another issue.",
        "",
        f"6. Perform the upgrade: bump `{dependency}` to `{target}` in the "
        "appropriate manifest(s) and lockfile(s), then apply the code changes "
        "required by the breaking changes and deprecations you identified so "
        "the project builds and its tests pass.",
        "",
        "7. Open a pull request with the upgrade. Include the current version, "
        "target version, migration steps, and validation performed, and link the "
        "original request issue. Do NOT include the impact report content in the "
        "PR description and do not add any report file to the PR.",
        "",
        "8. Handle the deprecations from the \"New deprecations\" category. For "
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
        "9. Assess the \"Changes to existing functionality\" category for "
        "behavioral impact. For each such change, determine whether it would "
        "actually affect the behavior of THIS codebase given how it uses the "
        "affected functionality (consider the arguments passed, the return "
        "values relied on, and the surrounding logic at each usage site). If "
        "any change would impact the codebase's behavior, prepare a Behavioral "
        "Impact Report in Markdown for HUMAN REVIEW that, for each impacted "
        "usage, describes the behavioral change, links to the affected code "
        f"({repo_url}/blob/<commit-sha>/<path>#L<line>), and explains the likely "
        "effect on the codebase. Keep this report only in the session context "
        "for the final original-issue comment; do not create or commit a report "
        "file. If no change has any behavioral impact, record `None` for this "
        "report in the completion comment.",
        "",
        "10. Handle the \"New functionality that can be used in the codebase\" "
        f"category. If there is new functionality in `{dependency}` that could "
        f"improve the codebase, open a GitHub issue in {repo_url} that "
        f"describes: the dependency upgrade (`{dependency}` from the current "
        f"version to `{target}`), the new functionality that is now available, "
        "and where in the codebase (with links to the relevant code) the new "
        "functionality could be used to improve the code. If there is no "
        "applicable new functionality, skip this step.",
    ]

    if issue_number is not None or issue_url:
        ref = issue_url or f"#{issue_number}"
        lines += [
            "",
            "11. After ALL upgrade work is complete and immediately before "
            "finishing the Devin session, add a completion comment to the "
            f"original GitHub issue {ref}. The comment MUST:",
            "",
            "   - Include every generated report directly in this comment, "
            "including the Dependency Upgrade Report, the Behavioral Impact "
            "Report when applicable, and any other report. Put each report's "
            "complete Markdown content in its own collapsible `<details>` "
            "section.",
            "   - This completion comment MUST be the only location containing "
            "the report content. Do not create, write, stage, commit, attach, or "
            "link to report files, and do not copy reports into pull request "
            "descriptions or other GitHub issues.",
            "   - List and link every pull request created during the session, "
            "including the main upgrade PR and any deprecation PRs.",
            "   - List and link every GitHub issue created during the session, "
            "including deprecation follow-ups and new-functionality proposals.",
            "   - State `None` for reports, pull requests, or issues when that "
            "artifact type has no entries.",
            "",
            "   Perform this GitHub interaction yourself using the GitHub access "
            "available inside this Devin session. The webhook service does not "
            "have or use GitHub API credentials.",
            "",
            "   Do not post this completion comment until the work and artifact "
            "lists are final. Check for the completion marker supplied in the "
            "session-start follow-up message before posting so retries do not "
            "create a duplicate. Do not finish the session until the comment has "
            "been posted successfully.",
            "",
            f"This upgrade was requested via GitHub issue {ref}.",
        ]

    if issue_title:
        lines += ["", f"Issue title: {issue_title}"]
    if issue_body:
        lines += [f"Issue body:\n{issue_body.strip()}"]

    return "\n".join(lines)
