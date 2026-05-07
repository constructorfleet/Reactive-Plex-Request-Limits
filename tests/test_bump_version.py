from pathlib import Path

from tools.bump_version import bump_version, determine_bump, update_pyproject_version


def test_determine_bump_uses_single_release_label():
    assert determine_bump(["patch"]) == "patch"
    assert determine_bump(["minor"]) == "minor"
    assert determine_bump(["major"]) == "major"
    assert determine_bump(["breaking"]) == "major"


def test_determine_bump_requires_release_label():
    try:
        determine_bump(["documentation"])
    except ValueError as error:
        assert "exactly one release label" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_determine_bump_rejects_multiple_release_labels():
    try:
        determine_bump(["patch", "minor"])
    except ValueError as error:
        assert "exactly one release label" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_bump_version_updates_semver():
    assert bump_version("1.2.3", "patch") == "1.2.4"
    assert bump_version("1.2.3", "minor") == "1.3.0"
    assert bump_version("1.2.3", "major") == "2.0.0"


def test_update_pyproject_version(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "request-shock"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    assert update_pyproject_version(pyproject, "minor") == "0.2.0"
    assert 'version = "0.2.0"' in pyproject.read_text(encoding="utf-8")
