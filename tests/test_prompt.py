from prompt import (
    IMPACT_CATEGORIES,
    build_session_started_message,
    build_upgrade_prompt,
)


def test_session_started_message_requires_devin_to_comment_with_session_id():
    message = build_session_started_message(
        issue_url="https://github.com/your-org/your-repo/issues/42",
        session_id="devin-123",
        session_url="https://app.devin.ai/sessions/123",
        dependency="requests",
        target_version="2.32.0",
    )

    assert "FIRST task" in message
    assert "picked up and sent to Devin" in message
    assert "Devin session ID: `devin-123`" in message
    assert "https://github.com/your-org/your-repo/issues/42" in message
    assert "<!-- devin-dependency-upgrade-session:devin-123 -->" in message
    assert "<!-- devin-dependency-upgrade-complete:devin-123 -->" in message
    assert "webhook service does not have or use GitHub API credentials" in message


def test_prompt_includes_key_steps():
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="requests",
        target_version="2.32.0",
        issue_number=42,
        issue_url="https://github.com/your-org/your-repo/issues/42",
        issue_title="Upgrade requests to 2.32.0",
    )
    assert "requests" in prompt
    assert "2.32.0" in prompt
    assert "CURRENT version" in prompt
    assert "changelog" in prompt
    assert "release notes" in prompt
    assert "upgrade" in prompt.lower()
    assert "https://github.com/your-org/your-repo" in prompt
    assert "issues/42" in prompt


def test_prompt_uses_deepwiki_then_verifies_against_authoritative_sources():
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="requests",
        target_version="2.32.0",
    )

    deepwiki_step = prompt[
        prompt.index("2. Use Devin's DeepWiki functionality"):
        prompt.index("3. Research the official changelog")
    ]
    assert "FIRST research source" in deepwiki_step
    assert "target repository" in deepwiki_step
    assert "public source repository" in deepwiki_step
    assert "reusable indexed context" in deepwiki_step
    assert "not as the sole source of truth" in deepwiki_step
    assert "CURRENT checkout and exact commit" in deepwiki_step
    assert "continue without blocking" in deepwiki_step

    official_research_step = prompt[
        prompt.index("3. Research the official changelog"):
        prompt.index("4. Find EVERY usage")
    ]
    assert "release notes" in official_research_step
    assert "upgrade/migration guides" in official_research_step
    assert "confirm or correct the DeepWiki findings" in official_research_step


def test_prompt_defaults_to_latest_when_no_version():
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="lodash",
        target_version="",
    )
    assert "the latest version" in prompt


def test_prompt_includes_impact_report_and_categories():
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="requests",
        target_version="2.32.0",
    )
    # Asks for the report + evaluating changes against codebase usage.
    assert "IMPACT REPORT" in prompt
    assert "usage" in prompt.lower()
    assert "DEPENDENCY_UPGRADE_REPORT.md" in prompt

    # All four required categories are present.
    assert "Breaking changes" in prompt
    assert "New deprecations" in prompt
    assert "Changes to existing functionality" in prompt
    assert "New functionality that can be used in the codebase" in prompt
    assert len(IMPACT_CATEGORIES) == 4
    for heading, _ in IMPACT_CATEGORIES:
        assert heading in prompt

    # Report items must link to codebase locations.
    assert "#L<line>" in prompt or "path:line" in prompt
    assert "https://github.com/your-org/your-repo/blob/" in prompt


def test_prompt_handles_deprecations_with_pr_or_issue():
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="requests",
        target_version="2.32.0",
    )
    # Prefer a PR that replaces the deprecated usage...
    assert "separate pull request" in prompt.lower()
    assert "deprecated" in prompt.lower()
    # ...otherwise fall back to filing a GitHub issue with the required detail.
    assert "GitHub issue" in prompt
    assert "impacted" in prompt.lower()


def test_prompt_assesses_behavioral_impact_for_existing_functionality_changes():
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="requests",
        target_version="2.32.0",
    )
    assert "behavior" in prompt.lower()
    assert "BEHAVIORAL_IMPACT_REPORT.md" in prompt
    assert "human review" in prompt.lower()


def test_prompt_updates_original_issue_when_session_completes():
    issue_url = "https://github.com/your-org/your-repo/issues/42"
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="requests",
        target_version="2.32.0",
        issue_number=42,
        issue_url=issue_url,
    )

    completion_step = prompt[prompt.index("11. After ALL upgrade work is complete"):]
    assert issue_url in completion_step
    assert "DEPENDENCY_UPGRADE_REPORT.md" in completion_step
    assert "BEHAVIORAL_IMPACT_REPORT.md" in completion_step
    assert "complete Markdown content" in completion_step
    assert "every pull request" in completion_step
    assert "every GitHub issue" in completion_step
    assert "Do not finish the session" in completion_step
    assert "Perform this GitHub interaction yourself" in completion_step
    assert "webhook service does not have or use GitHub API credentials" in completion_step


def test_prompt_opens_issue_for_usable_new_functionality():
    prompt = build_upgrade_prompt(
        repo_url="https://github.com/your-org/your-repo",
        dependency="requests",
        target_version="2.32.0",
    )
    step = prompt[prompt.index("10. Handle"):]
    assert "new functionality that is now available" in step.lower()
    assert "GitHub issue" in step
    assert "improve the code" in step.lower()
