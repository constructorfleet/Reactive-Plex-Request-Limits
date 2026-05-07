from __future__ import annotations

ALLOWED_LABELS = ("patch", "minor", "major", "breaking")


def validate_release_labels(labels: list[str]) -> str:
    normalized = [label.strip().lower() for label in labels]
    release_labels = [label for label in normalized if label in ALLOWED_LABELS]
    if len(release_labels) != 1:
        allowed = ", ".join(ALLOWED_LABELS)
        raise ValueError(f"PR must have exactly one release label in: {allowed}")
    return release_labels[0]
