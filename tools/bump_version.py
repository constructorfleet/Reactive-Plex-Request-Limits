from __future__ import annotations

import argparse
import re
from pathlib import Path

from tools.release_labels import validate_release_labels


def determine_bump(labels: list[str]) -> str:
    bump = validate_release_labels(labels)
    return "major" if bump == "breaking" else bump


def bump_version(version: str, bump: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Unsupported version format: {version}")

    major, minor, patch = (int(part) for part in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump type: {bump}")


def update_pyproject_version(path: Path, bump: str) -> str:
    content = path.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', content)
    if not match:
        raise ValueError(f"No project version found in {path}")

    new_version = bump_version(match.group(1), bump)
    updated = content[: match.start(1)] + new_version + content[match.end(1) :]
    path.write_text(updated, encoding="utf-8")
    return new_version


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump pyproject.toml version from PR labels.")
    parser.add_argument("--labels", required=True, help="Comma-separated PR labels.")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()

    labels = [label for label in args.labels.split(",") if label.strip()]
    bump = determine_bump(labels)
    version = update_pyproject_version(args.pyproject, bump)
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
