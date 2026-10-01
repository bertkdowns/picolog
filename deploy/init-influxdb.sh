#!/bin/sh
set -eu

# This volume is initialized with the InfluxDB image's directory ownership.
# Generate only once and publish atomically, without logging the credential.
umask 077
directory=/var/lib/influxdb3/auth
mkdir -p "$directory"
if [ ! -s "$directory/admin-token.json" ]; then
    influxdb3 create token --admin --offline \
        --output-file "$directory/admin-token.json.tmp" >/dev/null
    mv "$directory/admin-token.json.tmp" "$directory/admin-token.json"
fi

# Explorer imports this connection for new browser sessions. Use JSON encoding so
# environment values are handled safely, and keep the credential out of logs.
python3 - <<'PY'
import json
import os
from pathlib import Path

token = os.environ.get("INFLUXDB_TOKEN") or json.loads(
    Path("/var/lib/influxdb3/auth/admin-token.json").read_text()
)["token"]
config = {
    "DEFAULT_INFLUX_SERVER": "http://influxdb:8181",
    "DEFAULT_INFLUX_DATABASE": os.environ.get("INFLUXDB_DATABASE", "picolog"),
    "DEFAULT_API_TOKEN": token,
    "DEFAULT_SERVER_NAME": "Pico TC-08",
}
path = Path("/home/influxdb3/.influxdb3/config.json")
temporary = path.with_suffix(".tmp")
temporary.write_text(json.dumps(config))
temporary.chmod(0o600)
temporary.replace(path)
PY
