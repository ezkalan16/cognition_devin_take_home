from dependency_parser import parse_dependency


def test_structured_body():
    body = "Dependency: requests\nVersion: 2.32.0"
    parsed = parse_dependency("Upgrade dependency", body)
    assert parsed.name == "requests"
    assert parsed.version == "2.32.0"
    assert parsed.is_complete


def test_at_token():
    parsed = parse_dependency("requests==2.32.0", "")
    assert parsed.name == "requests"
    assert parsed.version == "2.32.0"


def test_natural_language_with_v_prefix():
    parsed = parse_dependency("Bump lodash to v4.17.21", None)
    assert parsed.name == "lodash"
    assert parsed.version == "4.17.21"


def test_natural_language_upgrade_to_version():
    parsed = parse_dependency("Upgrade the dependency django to version 5.0.6", None)
    assert parsed.name == "django"
    assert parsed.version == "5.0.6"


def test_scoped_npm_package_at_token():
    parsed = parse_dependency("@babel/core@7.24.0", "")
    assert parsed.name == "@babel/core"
    assert parsed.version == "7.24.0"


def test_name_without_version():
    parsed = parse_dependency("Please upgrade numpy", "")
    assert parsed.name is None or parsed.version is None
    assert not parsed.is_complete
