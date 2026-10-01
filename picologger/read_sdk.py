#!/usr/bin/env python3
"""Read a single thermocouple on TC-08 channel 5 by default with Pico's SDK."""

import argparse
import json

from tc08_sdk import TC08


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, default=5, choices=range(1, 9))
    parser.add_argument("--type", default="T", choices=list("BEJKNRST"))
    parser.add_argument("--mains", type=int, default=50, choices=(50, 60))
    args = parser.parse_args()

    with TC08() as device:
        device.set_mains(args.mains)
        for channel in range(1, 9):
            device.set_channel(channel, args.type if channel == args.channel else None)
        values, overflow = device.read_single_celsius()
        print(json.dumps({
            "info": device.info(),
            "minimum_interval_ms": device.minimum_interval_ms(),
            "channel": args.channel,
            "thermocouple_type": args.type,
            "temperature_c": values[args.channel],
            "cjc_c": values[0],
            "overflow_flags": overflow,
        }, indent=2))


if __name__ == "__main__":
    main()
