# TC-08 diagnostics

`log_influxdb.py` is the continuous production reader. `tc08_sdk.py` wraps
Pico's official C API using Python `ctypes`. No Python packages are required.
Container setup and continuous logging are documented in the [main README](../README.md).

## Single-shot SDK read

Stop the continuous reader before opening the same device:

```sh
docker compose stop picologger
docker compose run --rm --no-deps picologger python3 read_sdk.py --channel 5 --type T --mains 50
docker compose run --rm --no-deps -e TC08_HARDWARE=1 picologger python3 -m unittest -v test_sdk
docker compose up -d
```

On the original test unit, the SDK returned approximately 23.04 C on channel 5
and 23.74 C for CJC.

## Host execution

For development outside Docker, use Python 3.10+ and install `libusbtc08` from
Pico's `picoscope7` Debian repository. Native ARM64 packages are available for
64-bit Raspberry Pi OS; an armhf process is unnecessary.

```sh
sudo apt update
sudo apt install libusbtc08
dpkg-query -W libusbtc08
file /opt/picoscope/lib/libusbtc08.so.2.0.0
python3 picologger/read_sdk.py --channel 5 --type T --mains 50
```

Set `USBTC08_LIBRARY` if the library is in a nonstandard location. For continuous
host logging, supply `INFLUXDB_TOKEN` and optionally `INFLUXDB_URL` and
`INFLUXDB_DATABASE`, then run `python3 picologger/log_influxdb.py`. CLI options
override environment defaults; see `--help`.

## Experimental raw USB reader

`read_raw_usb.py` uses the system `libusb-1.0` library directly:

```sh
python3 picologger/read_raw_usb.py --channel 5 --mains 50
python3 -m unittest discover -s picologger -p test_raw_usb.py -v
```

On the original test unit, consecutive raw and SDK readings were 23.055 C and
23.039 C, a difference of about 0.016 C at ambient temperature.

Limitations:

- A cold-attached unit must first be initialized by Pico's firmware loader.
- CJC conversion is only validated in the linear ambient region near 24 C.
- Only single-shot type-T conversion and 50/60 Hz rejection are implemented.
- The raw reader is a protocol-validation tool, not a production replacement.

See [PROTOCOL.md](PROTOCOL.md) for packet details. Optional tracing tools are
in `../tools`; the GDB script is invoked from the repository root.
