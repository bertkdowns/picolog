# USB TC-08 Protocol Notes (experimental raw USB reader)

These notes describe USB TC-08 hardware variant 3, tested with firmware 2.00
and Pico `libusbtc08 2.0.151-1r6217`. They are observations, not a vendor
specification.

## USB States

The unit uses VID/PID `0ce9:1000` in both states.

Firmware-loader state after a cold attachment:

```text
bcdUSB:    2.00
bcdDevice: 0.01
class:     vendor-specific
interface alternate settings: 0..3
runtime bulk candidates: OUT 0x01, IN 0x81 (plus loader endpoints)
```

Runtime state after Pico's library initializes the unit:

```text
bcdUSB:    1.00
bcdDevice: 2.00
product:   USB TC-08
interface 0, alternate setting 0
bulk OUT:  0x01, max packet 64
bulk IN:   0x81, max packet 64
```

The transition includes firmware loading and re-enumeration. That phase has
not been reimplemented. This is the main reason `read_raw_usb.py` is not a
standalone replacement for the official library after a cold plug or reboot.

## Runtime Commands

Commands are unframed byte strings written to bulk endpoint `0x01`.

| Bytes | Meaning | Confidence |
|---|---|---|
| `0a 02` | Select/initialize current runtime mode | High, reconstructed from `usb_tc08_open_unit` |
| `09 00` | Set 50 Hz mains rejection | High, reconstructed and tested |
| `09 01` | Set 60 Hz mains rejection | High, reconstructed from `usb_tc08_set_mains` |
| `02` | Start one single-shot conversion | High, reconstructed and tested |
| `07` | Firmware-state probe/initialization command | Low, observed during loader tracing |
| `04` | Loader/info command | Low, observed during loader tracing |

For a single enabled channel, Pico reports a minimum conversion interval of
900 ms. The raw client waits 1 second after command `02`, then requests 36
bytes from endpoint `0x81`.

Thermocouple type is not sent to the device for a single conversion. The
logger returns ADC measurements; type selection, CJC compensation, unit
conversion, and overflow handling occur on the host.

## Response

The 36-byte response consists of nine four-byte records:

| Offset | Record |
|---|---|
| `0..3` | Cold-junction sensor |
| `4..7` | Channel 1 |
| `8..11` | Channel 2 |
| `12..15` | Channel 3 |
| `16..19` | Channel 4 |
| `20..23` | Channel 5 |
| `24..27` | Channel 6 |
| `28..31` | Channel 7 |
| `32..35` | Channel 8 |

Within each record, the first byte is status/metadata. The remaining three
bytes are a big-endian signed 24-bit value. Pico masks the low four count bits:

```python
count = signed_big_endian_24(record[1:4]) & ~0x0f
```

Static analysis and live measurements give these scales:

```text
thermocouple channels: count * 9.313225746154785e-6 mV
CJC sensor:            count * 0.00014901161193847656 mV
```

Example channel-5 record from the ambient test was `01 ff f3 f3`, producing
approximately `-0.02861 mV`. The CJC sensor field produced `435.910 mV`; Pico's
internal CJC table converted this to `23.743 C`.

For type T, the host adds the NIST ITS-90 EMF at the CJC temperature to the
measured channel EMF, then applies the inverse NIST type-T polynomial.

## Remaining Work

A complete independent implementation still needs:

1. Legal extraction or independent acquisition of the loader firmware and
   reproduction of the firmware download/re-enumeration sequence.
2. The full CJC sensor lookup table and out-of-range behavior.
3. Status-byte and overflow-bit semantics.
4. Streaming commands, timing, packet loss behavior, and all thermocouple
   types.
5. Validation over the TC-08 temperature and voltage range against calibrated
   equipment.

Because Pico now ships native ARM64 `libusbtc08`, those reverse-engineering
steps are not required to deploy the logger on a 64-bit Raspberry Pi.
