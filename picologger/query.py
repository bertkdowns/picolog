#!/usr/bin/env python3
"""Run a SQL query using the logger's database and authentication settings."""

import argparse
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from influx_config import load_token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql", nargs="?", default=(
        "SELECT * FROM tc08 WHERE time >= now() - INTERVAL '1 hour' "
        "ORDER BY time DESC LIMIT 100"
    ))
    args = parser.parse_args()
    url = os.environ.get("INFLUXDB_URL", "http://localhost:8181").rstrip("/")
    query = urlencode({
        "db": os.environ.get("INFLUXDB_DATABASE", "picolog"),
        "q": args.sql, "format": "json",
    })
    request = Request(url + "/api/v3/query_sql?" + query, headers={
        "Authorization": "Bearer " + load_token(),
    })
    with urlopen(request, timeout=30) as response:
        print(response.read().decode())


if __name__ == "__main__":
    main()
