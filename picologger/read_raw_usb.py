#!/usr/bin/env python3
"""Experimental type-T read from a firmware-initialized TC-08 via libusb."""

import argparse
import json

from tc08_raw_usb import RawTC08


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, default=5, choices=range(1, 9))
    parser.add_argument("--mains", type=int, default=50, choices=(50, 60))
    args = parser.parse_args()

    with RawTC08() as device:
        device.initialize_measurement_mode()
        device.set_mains(args.mains)
        temperature_c, cjc_c, measured_mv = device.read_type_t_celsius(args.channel)
        print(json.dumps({
            "channel": args.channel,
            "thermocouple_type": "T",
            "temperature_c": temperature_c,
            "cjc_c": cjc_c,
            "channel_mv": measured_mv,
        }, indent=2))


if __name__ == "__main__":
    main()
