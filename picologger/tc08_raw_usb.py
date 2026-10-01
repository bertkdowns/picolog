#!/usr/bin/env python3
"""Experimental USB TC-08 access via libusb, without Pico's libusbtc08."""

from __future__ import annotations

import ctypes
import ctypes.util
import math
import time


VID = 0x0CE9
PID = 0x1000
ENDPOINT_OUT = 0x01
ENDPOINT_IN = 0x81
RESPONSE_SIZE = 36
CHANNEL_MV_PER_COUNT = 9.313225746154785e-6
CJC_MV_PER_COUNT = 0.00014901161193847656
# Pico's driver uses an internal lookup table for this sensor. These linear
# region values were cross-checked against the official driver near 24 C.
CJC_AMBIENT_MV_PER_C = 10.0
CJC_AMBIENT_ZERO_C_MV = 198.4783935546875


class RawTC08Error(RuntimeError):
    pass


class DeviceDescriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16),
        ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8),
        ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8),
        ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16),
        ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8),
        ("iProduct", ctypes.c_uint8),
        ("iSerialNumber", ctypes.c_uint8),
        ("bNumConfigurations", ctypes.c_uint8),
    ]


def _polynomial(x: float, coefficients: tuple[float, ...]) -> float:
    result = 0.0
    for coefficient in reversed(coefficients):
        result = result * x + coefficient
    return result


def type_t_c_to_mv(temperature_c: float) -> float:
    if not -270.0 <= temperature_c <= 400.0:
        raise ValueError("type-T reference temperature is outside -270..400 C")
    if temperature_c < 0:
        coefficients = (
            0.0, 0.387481063640e-1, 0.441944343470e-4,
            0.118443231050e-6, 0.200329735540e-7,
            0.901380195590e-9, 0.226511565930e-10,
            0.360711542050e-12, 0.384939398830e-14,
            0.282135219250e-16, 0.142515947790e-18,
            0.487686622860e-21, 0.107955392700e-23,
            0.139450270620e-26, 0.797951539270e-30,
        )
    else:
        coefficients = (
            0.0, 0.387481063640e-1, 0.332922278800e-4,
            0.206182434040e-6, -0.218822568460e-8,
            0.109968809280e-10, -0.308157587720e-13,
            0.454791352900e-16, -0.275129016730e-19,
        )
    return _polynomial(temperature_c, coefficients)


def type_t_mv_to_c(millivolts: float) -> float:
    if -5.603 <= millivolts < 0:
        coefficients = (
            0.0, 2.5949192e1, -2.1316967e-1, 7.9018692e-1,
            4.2527777e-1, 1.3304473e-1, 2.0241446e-2,
            1.2668171e-3,
        )
    elif 0 <= millivolts <= 20.872:
        coefficients = (
            0.0, 2.592800e1, -7.602961e-1, 4.637791e-2,
            -2.165394e-3, 6.048144e-5, -7.293422e-7,
        )
    else:
        raise ValueError("type-T EMF is outside -5.603..20.872 mV")
    return _polynomial(millivolts, coefficients)


def _signed_24(data: bytes) -> int:
    value = int.from_bytes(data, "big", signed=False)
    if value & 0x800000:
        value -= 1 << 24
    return value & ~0xF


def parse_response(packet: bytes) -> tuple[float, list[float]]:
    if len(packet) != RESPONSE_SIZE:
        raise RawTC08Error(f"expected {RESPONSE_SIZE} response bytes, got {len(packet)}")
    cjc_sensor_mv = _signed_24(packet[1:4]) * CJC_MV_PER_COUNT
    channel_mv = [
        _signed_24(packet[offset + 1 : offset + 4]) * CHANNEL_MV_PER_COUNT
        for offset in range(4, RESPONSE_SIZE, 4)
    ]
    return cjc_sensor_mv, channel_mv


def ambient_cjc_mv_to_c(sensor_mv: float) -> float:
    """Convert the CJC sensor in the ambient region validated on this unit."""
    return (sensor_mv - CJC_AMBIENT_ZERO_C_MV) / CJC_AMBIENT_MV_PER_C


class RawTC08:
    def __init__(self) -> None:
        library = ctypes.util.find_library("usb-1.0")
        if not library:
            raise RawTC08Error("libusb-1.0 is not installed")
        self.usb = ctypes.CDLL(library)
        self.context = ctypes.c_void_p()
        self.handle = ctypes.c_void_p()
        self._configure_abi()

    def _configure_abi(self) -> None:
        self.usb.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self.usb.libusb_init.restype = ctypes.c_int
        self.usb.libusb_exit.argtypes = [ctypes.c_void_p]
        self.usb.libusb_open_device_with_vid_pid.argtypes = [
            ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16
        ]
        self.usb.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p
        self.usb.libusb_get_device.argtypes = [ctypes.c_void_p]
        self.usb.libusb_get_device.restype = ctypes.c_void_p
        self.usb.libusb_get_device_descriptor.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(DeviceDescriptor)
        ]
        self.usb.libusb_get_device_descriptor.restype = ctypes.c_int
        self.usb.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.usb.libusb_claim_interface.restype = ctypes.c_int
        self.usb.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.usb.libusb_release_interface.restype = ctypes.c_int
        self.usb.libusb_close.argtypes = [ctypes.c_void_p]
        self.usb.libusb_bulk_transfer.argtypes = [
            ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
        ]
        self.usb.libusb_bulk_transfer.restype = ctypes.c_int

    def open(self) -> "RawTC08":
        result = self.usb.libusb_init(ctypes.byref(self.context))
        if result:
            raise RawTC08Error(f"libusb_init failed ({result})")
        self.handle = self.usb.libusb_open_device_with_vid_pid(self.context, VID, PID)
        if not self.handle:
            self.usb.libusb_exit(self.context)
            self.context = ctypes.c_void_p()
            raise RawTC08Error("USB TC-08 0ce9:1000 was not found or is not accessible")

        descriptor = DeviceDescriptor()
        device = self.usb.libusb_get_device(self.handle)
        result = self.usb.libusb_get_device_descriptor(device, ctypes.byref(descriptor))
        if result:
            self.close()
            raise RawTC08Error(f"could not read device descriptor ({result})")
        if descriptor.bcdDevice < 0x0200:
            self.close()
            raise RawTC08Error(
                "TC-08 is in its firmware-loader state (bcdDevice < 2.00); "
                "initialize it once with Pico's driver before using raw mode"
            )
        result = self.usb.libusb_claim_interface(self.handle, 0)
        if result:
            self.close()
            raise RawTC08Error(f"could not claim USB interface 0 ({result})")
        return self

    def close(self) -> None:
        if self.handle:
            self.usb.libusb_release_interface(self.handle, 0)
            self.usb.libusb_close(self.handle)
            self.handle = ctypes.c_void_p()
        if self.context:
            self.usb.libusb_exit(self.context)
            self.context = ctypes.c_void_p()

    def __enter__(self) -> "RawTC08":
        return self.open()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _write(self, payload: bytes) -> None:
        buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
        transferred = ctypes.c_int()
        result = self.usb.libusb_bulk_transfer(
            self.handle, ENDPOINT_OUT, buffer, len(buffer),
            ctypes.byref(transferred), 2000,
        )
        if result or transferred.value != len(payload):
            raise RawTC08Error(
                f"USB write failed ({result}, {transferred.value}/{len(payload)} bytes)"
            )

    def _read(self, length: int) -> bytes:
        buffer = (ctypes.c_ubyte * length)()
        transferred = ctypes.c_int()
        result = self.usb.libusb_bulk_transfer(
            self.handle, ENDPOINT_IN, buffer, length,
            ctypes.byref(transferred), 2000,
        )
        if result:
            raise RawTC08Error(f"USB read failed ({result})")
        return bytes(buffer[: transferred.value])

    def initialize_measurement_mode(self) -> None:
        self._write(b"\x0a\x02")

    def set_mains(self, hz: int) -> None:
        if hz not in (50, 60):
            raise ValueError("mains frequency must be 50 or 60 Hz")
        self._write(bytes((0x09, int(hz == 60))))

    def read_raw(self, conversion_seconds: float = 1.0) -> tuple[float, list[float], bytes]:
        self._write(b"\x02")
        time.sleep(conversion_seconds)
        packet = self._read(RESPONSE_SIZE)
        cjc_sensor_mv, channel_mv = parse_response(packet)
        return cjc_sensor_mv, channel_mv, packet

    def read_type_t_celsius(self, channel: int = 5) -> tuple[float, float, float]:
        if channel not in range(1, 9):
            raise ValueError("channel must be in the range 1..8")
        cjc_sensor_mv, channel_mv, _ = self.read_raw()
        cjc_c = ambient_cjc_mv_to_c(cjc_sensor_mv)
        compensated_mv = channel_mv[channel - 1] + type_t_c_to_mv(cjc_c)
        temperature_c = type_t_mv_to_c(compensated_mv)
        if not math.isfinite(temperature_c):
            raise RawTC08Error("temperature conversion produced a non-finite result")
        return temperature_c, cjc_c, channel_mv[channel - 1]
