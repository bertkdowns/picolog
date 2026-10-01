#!/usr/bin/env python3
"""Tests for the experimental raw USB conversion functions."""

import unittest

from tc08_raw_usb import parse_response, type_t_c_to_mv, type_t_mv_to_c


class ConversionTests(unittest.TestCase):
    def test_type_t_round_trip(self) -> None:
        for expected in (-100.0, -10.0, 0.0, 25.0, 100.0, 300.0):
            actual = type_t_mv_to_c(type_t_c_to_mv(expected))
            self.assertAlmostEqual(actual, expected, delta=0.06)

    def test_zero_packet(self) -> None:
        cjc_sensor_mv, channels_mv = parse_response(bytes(36))
        self.assertEqual(cjc_sensor_mv, 0.0)
        self.assertEqual(channels_mv, [0.0] * 8)


if __name__ == "__main__":
    unittest.main()
