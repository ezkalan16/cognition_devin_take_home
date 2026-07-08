from prompt import build_upgrade_prompt


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
