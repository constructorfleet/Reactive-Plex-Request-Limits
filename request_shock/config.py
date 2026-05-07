from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

import yaml

from request_shock.policy import Limits, PolicyConfig


def load_config(path: Path) -> tuple[dict[str, Any], PolicyConfig]:
    data = yaml.safe_load(path.read_text()) or {}
    policy_data = data.get("policy", {})
    limits = {}
    for key in ("normal_limits", "warning_limits", "restricted_limits"):
        if key in policy_data:
            limits[key] = Limits(**policy_data.pop(key))
    allowed = {field.name for field in fields(PolicyConfig)}
    policy_kwargs = {key: value for key, value in policy_data.items() if key in allowed}
    return data, PolicyConfig(**limits, **policy_kwargs)
