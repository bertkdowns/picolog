"""Configuration tests for container and host authentication."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from influx_config import load_token


class TokenTests(unittest.TestCase):
    def test_generated_offline_token_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "admin-token.json"
            path.write_text(json.dumps({"token": "apiv3_example", "name": "_admin"}))
            with patch.dict(os.environ, {"INFLUXDB_TOKEN_FILE": str(path)}, clear=True):
                self.assertEqual(load_token(), "apiv3_example")

    def test_existing_token_overrides_file(self):
        with patch.dict(os.environ, {
            "INFLUXDB_TOKEN": "existing-token",
            "INFLUXDB_TOKEN_FILE": "/missing-file",
        }, clear=True):
            self.assertEqual(load_token(), "existing-token")

    def test_missing_configuration_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            load_token()

    def test_empty_token_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "admin-token.json"
            path.write_text('{"token": ""}')
            with patch.dict(os.environ, {"INFLUXDB_TOKEN_FILE": str(path)}, clear=True):
                with self.assertRaises(ValueError):
                    load_token()


if __name__ == "__main__":
    unittest.main()
