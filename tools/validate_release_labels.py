from __future__ import annotations

import argparse

from tools.release_labels import validate_release_labels


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pull request release labels.")
    parser.add_argument("--labels", required=True, help="Comma-separated PR labels.")
    args = parser.parse_args()

    labels = [label for label in args.labels.split(",") if label.strip()]
    selected = validate_release_labels(labels)
    print(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
