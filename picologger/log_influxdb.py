#!/usr/bin/env python3
"""Continuously record TC-08 temperatures in InfluxDB 3 (stdlib only)."""

from __future__ import annotations

import argparse
import logging
import math
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tc08_sdk import TC08
from influx_config import load_token


def tag(value: str) -> str:
    if not value or any(c in value for c in "\r\n"):
        raise ValueError("tags must be nonempty and contain no newlines")
    return value.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def sample_lines(values, overflow, channels, device_id, timestamp_ns):
    """Preserve all configured readings, including status for invalid values."""
    lines = []
    for channel, kind in [(0, "CJC"), *sorted(channels.items())]:
        value = values[channel]
        finite = math.isfinite(value)
        fields = [
            f"overflow_flags={overflow}i",
            f"valid={str(finite and not (overflow & (1 << channel))).lower()}",
        ]
        if finite:
            fields.append(f"temperature_c={float(value)!r}")
        lines.append(
            f"tc08,device={tag(device_id)},channel={channel},thermocouple_type={kind} "
            f"{','.join(fields)} {timestamp_ns}"
        )
    return "\n".join(lines)


class Outbox:
    """Commit locally before upload; acknowledge only whole successful batches."""

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS pending (id INTEGER PRIMARY KEY, lines TEXT NOT NULL)"
        )
        self.db.commit()

    def add(self, lines):
        with self.db:
            self.db.execute("INSERT INTO pending (lines) VALUES (?)", (lines,))

    def flush(self, writer):
        rows = self.db.execute("SELECT id, lines FROM pending ORDER BY id LIMIT 100").fetchall()
        if not rows:
            return 0
        writer.write("\n".join(row[1] for row in rows))
        with self.db:
            self.db.executemany("DELETE FROM pending WHERE id = ?", [(row[0],) for row in rows])
        return len(rows)

    def close(self):
        self.db.close()


class InfluxWriter:
    def __init__(self, url, database, token):
        self.url = url.rstrip("/") + "/api/v3/write_lp?" + urlencode({
            "db": database, "precision": "nanosecond", "accept_partial": "false",
        })
        self.token = token

    def write(self, lines):
        request = Request(self.url, data=lines.encode(), method="POST", headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "text/plain; charset=utf-8",
        })
        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 204:
                    raise RuntimeError(f"unexpected InfluxDB status {response.status}")
        except HTTPError as error:
            detail = error.read(2048).decode(errors="replace")
            raise RuntimeError(f"InfluxDB HTTP {error.code}: {detail}") from None


def upload_loop(path, writer, stop):
    outbox = Outbox(path)
    try:
        while not stop.is_set():
            try:
                count = outbox.flush(writer)
                if count:
                    logging.info("Uploaded %d queued samples", count)
                    continue
            except (RuntimeError, URLError, OSError) as error:
                logging.warning("Upload failed; readings retained locally: %s", error)
                stop.wait(5)
                continue
            stop.wait(0.5)
    finally:
        outbox.close()


def channel_config(value):
    try:
        result = {}
        for item in value.split(","):
            number, kind = item.split(":")
            number, kind = int(number), kind.upper()
            if number not in range(1, 9) or kind not in list("BEJKNRST") or number in result:
                raise ValueError
            result[number] = kind
        return result
    except ValueError:
        raise argparse.ArgumentTypeError("use unique channel:type pairs, e.g. 1:T,5:K (channels 1..8)") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", type=channel_config, default=os.environ.get("TC08_CHANNELS", "1:T,2:T,3:T,4:T,5:T,6:T,7:T,8:T"))
    parser.add_argument("--mains", type=int, choices=(50, 60), default=os.environ.get("TC08_MAINS", "50"))
    parser.add_argument("--interval", type=float, default=os.environ.get("TC08_INTERVAL", "5"), help="seconds between acquisition starts (default: 5)")
    parser.add_argument("--device-id", default=os.environ.get("TC08_DEVICE_ID"), help="defaults to the unit's batch/serial number")
    parser.add_argument("--url", default=os.environ.get("INFLUXDB_URL", "http://localhost:8181"))
    parser.add_argument("--database", default=os.environ.get("INFLUXDB_DATABASE", "picolog"))
    parser.add_argument("--spool", default="data/picolog.sqlite3", help="persistent local upload queue")
    args = parser.parse_args()
    try:
        token = load_token()
    except (OSError, ValueError, KeyError) as error:
        parser.error(f"cannot load InfluxDB token: {error}")
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error("--interval must be a finite positive number")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    writer = InfluxWriter(args.url, args.database, token)
    outbox = Outbox(args.spool)
    worker = threading.Thread(target=upload_loop, args=(args.spool, writer, stop), daemon=True)
    worker.start()
    try:
        logging.info("Opening TC-08; firmware initialization may take a minute")
        with TC08() as device:
            device.set_mains(args.mains)
            for channel in range(1, 9):
                device.set_channel(channel, args.channels.get(channel))
            device_id = args.device_id or device.info()["batch_and_serial"]
            tag(device_id)
            interval = max(args.interval, device.minimum_interval_ms() / 1000)
            logging.info("Recording %s channels %s plus CJC every %.3fs", device_id, sorted(args.channels), interval)
            while not stop.is_set():
                if not worker.is_alive():
                    raise RuntimeError("upload worker stopped; check preceding error")
                started = time.monotonic()
                values, overflow = device.read_single_celsius()
                outbox.add(sample_lines(values, overflow, args.channels, device_id, time.time_ns()))
                stop.wait(max(0, interval - (time.monotonic() - started)))
    finally:
        stop.set()
        worker.join()
        outbox.close()
        logging.info("Stopped; any pending samples will upload on the next run")


if __name__ == "__main__":
    main()
