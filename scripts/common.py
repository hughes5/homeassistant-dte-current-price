from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


def load_data(data_dir: str | Path) -> dict[str, Any]:
    path = Path(data_dir) / "data.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        print(f"ERROR: {path} is empty or not a valid YAML mapping")
        sys.exit(1)

    required_keys = {"pscr", "securitization", "delivery_surcharge", "distribution", "schedules"}
    missing = required_keys - set(data.keys())
    if missing:
        print(f"ERROR: {path} missing required keys: {', '.join(sorted(missing))}")
        sys.exit(1)

    return data
