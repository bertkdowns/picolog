"""Storage tests; no Pico hardware required."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from log_influxdb import InfluxWriter, Outbox, channel_config, sample_lines
from influx_config import load_token


class StorageTests(unittest.TestCase):
    def test_all_channels_and_cjc_share_timestamp(self):
        lines = sample_lines([23.5] * 9, 1 << 5, {i: "T" for i in range(1, 9)}, "unit A,=1", 123)
        self.assertEqual(len(lines.splitlines()), 9)
        self.assertTrue(all(line.endswith(" 123") for line in lines.splitlines()))
        self.assertIn("device=unit\\ A\\,\\=1,channel=0,thermocouple_type=CJC", lines)
        self.assertIn("channel=5,thermocouple_type=T overflow_flags=32i,valid=false", lines)
        self.assertIn("channel=6,thermocouple_type=T overflow_flags=32i,valid=true", lines)

    def test_nonfinite_reading_keeps_status_without_invalid_line_protocol(self):
        lines = sample_lines([23.5, float("nan"), float("inf")], 0, {1: "T", 2: "K"}, "unit", 123).splitlines()
        for line in lines[1:]:
            self.assertIn("valid=false", line)
            self.assertNotIn("temperature_c", line)

    def test_mixed_types_and_bad_channel_configuration(self):
        self.assertEqual(channel_config("1:t,5:K"), {1: "T", 5: "K"})
        for value in ("", "0:T", "9:T", "1:X", "1:T,1:K", "1:BE"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                channel_config(value)

    def test_failed_upload_survives_restart_and_replays_original_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            outbox = Outbox(path)
            lines = sample_lines([23.5] * 9, 0, {5: "T"}, "unit", 123)
            outbox.add(lines)
            writer = Mock()
            writer.write.side_effect = RuntimeError("server unavailable")
            with self.assertRaises(RuntimeError):
                outbox.flush(writer)
            outbox.close()
            outbox = Outbox(path)
            writer.write.side_effect = None
            self.assertEqual(outbox.flush(writer), 1)
            writer.write.assert_called_with(lines)
            self.assertEqual(outbox.flush(writer), 0)
            outbox.close()

    def test_concurrent_acquisition_is_not_deleted_when_batch_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            producer, consumer = Outbox(path), Outbox(path)
            producer.add("first")
            writer = Mock()
            writer.write.side_effect = lambda _: producer.add("second")
            self.assertEqual(consumer.flush(writer), 1)
            writer.write.side_effect = None
            self.assertEqual(consumer.flush(writer), 1)
            writer.write.assert_called_with("second")
            producer.close()
            consumer.close()


@unittest.skipUnless(os.environ.get("INFLUXDB_INTEGRATION") == "1", "live InfluxDB test")
class LiveInfluxTests(unittest.TestCase):
    def test_write_query_and_idempotent_replay(self):
        url = os.environ.get("INFLUXDB_URL", "http://localhost:8181")
        token = load_token()
        database = "picolog_test_" + str(time.time_ns())
        writer = InfluxWriter(url, database, token)
        timestamp = time.time_ns()
        lines = sample_lines([23.5] * 9, 32, {i: "T" for i in range(1, 9)}, "test unit,=1", timestamp)
        writer.write(lines)
        writer.write(lines)
        query = urlencode({"db": database, "q": "SELECT * FROM tc08 ORDER BY channel", "format": "json"})
        with urlopen(Request(url + "/api/v3/query_sql?" + query, headers={"Authorization": "Bearer " + token}), timeout=10) as response:
            rows = json.load(response)
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0]["thermocouple_type"], "CJC")
        self.assertEqual(rows[5]["temperature_c"], 23.5)
        self.assertFalse(rows[5]["valid"])
        self.assertTrue(rows[6]["valid"])
        self.assertEqual(rows[0]["device"], "test unit,=1")
        # Invalid authentication must fail without acknowledging the local queue.
        with tempfile.TemporaryDirectory() as directory:
            outbox = Outbox(Path(directory) / "queue.sqlite3")
            outbox.add(lines)
            try:
                with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                    outbox.flush(InfluxWriter(url, database, "invalid-token"))
                self.assertEqual(outbox.flush(writer), 1)
            finally:
                outbox.close()


if __name__ == "__main__":
    unittest.main()
