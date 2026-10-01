"""Shared authentication for the logger and command-line query helper."""

import json
import os
from pathlib import Path


def load_token() -> str:
    token = os.environ.get("INFLUXDB_TOKEN", "")
    if not token:
        path = os.environ.get("INFLUXDB_TOKEN_FILE")
        if not path:
            raise ValueError("set INFLUXDB_TOKEN or INFLUXDB_TOKEN_FILE")
        token = json.loads(Path(path).read_text())["token"]
    if not isinstance(token, str) or not token.strip():
        raise ValueError("InfluxDB token must be a nonempty string")
    return token.strip()
