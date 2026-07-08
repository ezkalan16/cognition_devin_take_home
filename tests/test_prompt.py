from prompt import IMPACT_CATEGORIES, build_upgrade_prompt


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
