import pytest

from tools.validate_release_labels import main


def test_validate_release_labels_cli_prints_selected_label(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["validate-release-labels", "--labels", "docs,minor"])

    assert main() == 0
    assert capsys.readouterr().out.strip() == "minor"


def test_validate_release_labels_cli_rejects_invalid_labels(monkeypatch):
    monkeypatch.setattr("sys.argv", ["validate-release-labels", "--labels", "docs"])

    with pytest.raises(ValueError):
        main()
