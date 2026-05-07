from tools.release_labels import ALLOWED_LABELS, validate_release_labels


def test_validate_release_labels_requires_exactly_one_allowed_label():
    assert validate_release_labels(["patch"]) == "patch"
    assert validate_release_labels(["documentation", "minor"]) == "minor"
    assert validate_release_labels(["breaking"]) == "breaking"


def test_validate_release_labels_rejects_missing_release_label():
    try:
        validate_release_labels(["documentation", "dependencies"])
    except ValueError as error:
        assert "exactly one" in str(error)
        assert ", ".join(ALLOWED_LABELS) in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_validate_release_labels_rejects_multiple_release_labels():
    try:
        validate_release_labels(["patch", "minor"])
    except ValueError as error:
        assert "exactly one" in str(error)
    else:
        raise AssertionError("expected ValueError")
