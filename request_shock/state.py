from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from request_shock.policy import StateEntry


def load_state(path: Path) -> dict[str, StateEntry]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {str(user_id): StateEntry(**entry) for user_id, entry in data.items()}


def save_state(path: Path, state: dict[str, StateEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: asdict(value) for key, value in state.items()}, indent=2, sort_keys=True))


def updated_entry(score: int, reason: str) -> StateEntry:
    return StateEntry(score=score, last_reason=reason, updated_at=datetime.now(UTC).isoformat())
