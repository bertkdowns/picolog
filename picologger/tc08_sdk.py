#!/usr/bin/env python3
"""Minimal ctypes client for Pico's official USB TC-08 SDK."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


CHANNEL_COUNT = 9  # CJC at index 0, thermocouple inputs at 1..8.
CELSIUS = 0


class TC08Error(RuntimeError):
    pass


def _library_path() -> str:
    override = os.environ.get("USBTC08_LIBRARY")
    if override:
        return override

    installed = Path("/opt/picoscope/lib/libusbtc08.so.2.0.0")
    if installed.exists():
        return str(installed)

    local = (
        Path(__file__).resolve().parent.parent
        / "local-artifacts/vendor/libusbtc08/opt/picoscope/lib/libusbtc08.so.2.0.0"
    )
    if local.exists():
        return str(local)
    return "libusbtc08.so"


def load_library() -> ctypes.CDLL:
    lib = ctypes.CDLL(_library_path())
    lib.usb_tc08_open_unit.argtypes = []
    lib.usb_tc08_open_unit.restype = ctypes.c_int16
    lib.usb_tc08_close_unit.argtypes = [ctypes.c_int16]
    lib.usb_tc08_close_unit.restype = ctypes.c_int16
    lib.usb_tc08_get_last_error.argtypes = [ctypes.c_int16]
    lib.usb_tc08_get_last_error.restype = ctypes.c_int16
    lib.usb_tc08_set_mains.argtypes = [ctypes.c_int16, ctypes.c_int16]
    lib.usb_tc08_set_mains.restype = ctypes.c_int16
    lib.usb_tc08_set_channel.argtypes = [
        ctypes.c_int16,
        ctypes.c_int16,
        ctypes.c_int8,
    ]
    lib.usb_tc08_set_channel.restype = ctypes.c_int16
    lib.usb_tc08_get_minimum_interval_ms.argtypes = [ctypes.c_int16]
    lib.usb_tc08_get_minimum_interval_ms.restype = ctypes.c_int32
    lib.usb_tc08_get_single.argtypes = [
        ctypes.c_int16,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_int16),
        ctypes.c_int16,
    ]
    lib.usb_tc08_get_single.restype = ctypes.c_int16
    lib.usb_tc08_get_unit_info2.argtypes = [
        ctypes.c_int16,
        ctypes.POINTER(ctypes.c_int8),
        ctypes.c_int16,
        ctypes.c_int16,
    ]
    lib.usb_tc08_get_unit_info2.restype = ctypes.c_int16
    return lib


class TC08:
    def __init__(self, library: ctypes.CDLL | None = None) -> None:
        self.lib = library or load_library()
        self.handle = 0

    def _error(self, operation: str) -> TC08Error:
        code = self.lib.usb_tc08_get_last_error(self.handle)
        return TC08Error(f"{operation} failed (TC-08 error {code})")

    def open(self) -> "TC08":
        self.handle = self.lib.usb_tc08_open_unit()
        if self.handle <= 0:
            raise self._error("usb_tc08_open_unit")
        return self

    def close(self) -> None:
        if self.handle:
            if not self.lib.usb_tc08_close_unit(self.handle):
                raise self._error("usb_tc08_close_unit")
            self.handle = 0

    def __enter__(self) -> "TC08":
        return self.open()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def set_mains(self, hz: int) -> None:
        if hz not in (50, 60):
            raise ValueError("mains frequency must be 50 or 60 Hz")
        if not self.lib.usb_tc08_set_mains(self.handle, hz == 60):
            raise self._error("usb_tc08_set_mains")

    def set_channel(self, channel: int, thermocouple_type: str | None) -> None:
        if channel not in range(1, CHANNEL_COUNT):
            raise ValueError("channel must be in the range 1..8")
        value = ord(thermocouple_type.upper()) if thermocouple_type else 0
        if not self.lib.usb_tc08_set_channel(self.handle, channel, value):
            raise self._error("usb_tc08_set_channel")

    def minimum_interval_ms(self) -> int:
        interval = self.lib.usb_tc08_get_minimum_interval_ms(self.handle)
        if interval <= 0:
            raise self._error("usb_tc08_get_minimum_interval_ms")
        return interval

    def read_single_celsius(self) -> tuple[list[float], int]:
        values = (ctypes.c_float * CHANNEL_COUNT)()
        overflow = ctypes.c_int16()
        if not self.lib.usb_tc08_get_single(
            self.handle, values, ctypes.byref(overflow), CELSIUS
        ):
            raise self._error("usb_tc08_get_single")
        return list(values), overflow.value

    def info(self) -> dict[str, str]:
        names = (
            "driver_version",
            "kernel_driver_version",
            "hardware_version",
            "variant",
            "batch_and_serial",
            "calibration_date",
            "driver_path",
        )
        result = {}
        for line, name in enumerate(names):
            buffer = (ctypes.c_int8 * 256)()
            # Some Linux builds return zero for unsupported info lines while
            # leaving the driver's last-error value at OK.
            self.lib.usb_tc08_get_unit_info2(self.handle, buffer, len(buffer), line)
            result[name] = bytes(buffer).split(b"\0", 1)[0].decode(errors="replace")
        return result
