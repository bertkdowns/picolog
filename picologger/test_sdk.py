#!/usr/bin/env python3
"""Unit and opt-in hardware tests for the USB TC-08 SDK wrapper."""

import math
import os
import unittest

from tc08_sdk import TC08, load_library


class LibraryTests(unittest.TestCase):
    def test_official_library_loads(self) -> None:
        library = load_library()
        self.assertTrue(hasattr(library, "usb_tc08_open_unit"))

    @unittest.skipUnless(os.environ.get("TC08_HARDWARE") == "1", "hardware test")
    def test_channel_5_type_t_ambient_reading(self) -> None:
        with TC08() as device:
            device.set_mains(50)
            for channel in range(1, 9):
                device.set_channel(channel, "T" if channel == 5 else None)
            temperatures, overflow = device.read_single_celsius()

            self.assertEqual(len(temperatures), 9)
            self.assertTrue(math.isfinite(temperatures[0]), "invalid CJC reading")
            self.assertTrue(math.isfinite(temperatures[5]), "invalid channel 5 reading")
            self.assertGreater(temperatures[0], -10.0)
            self.assertLess(temperatures[0], 60.0)
            self.assertGreater(temperatures[5], -10.0)
            self.assertLess(temperatures[5], 60.0)
            self.assertEqual(overflow & (1 << 5), 0, "channel 5 overflowed")


if __name__ == "__main__":
    unittest.main()
