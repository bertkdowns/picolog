# Pico TC-08 → InfluxDB 3

Continuously record all eight thermocouple inputs plus the cold-junction (CJC)
temperature in InfluxDB 3 Core. Everything runs with Docker Compose, including
Pico's official USB driver and automatic database authentication setup.

## Start everything

On the Linux machine connected to the TC-08:

```sh
docker compose up -d
```

This builds InfluxDB and the logger on first use, creates a persistent administrator
token, starts InfluxDB, waits for its health check, and starts USB acquisition.
No host Python, Pico driver installation, manual token creation, or `.env` file
is required. The database and table are created on the first successful upload.

Requirements:

- Docker Engine with the Compose v2 plugin (rootful Docker).
- Linux AMD64 or **64-bit Raspberry Pi OS / ARM64**.
- A connected Pico USB TC-08, with `/dev/bus/usb` available on the host.
- Internet access for the initial image build/download.

`docker compose up` runs the same stack in the foreground. `docker-compose up`
also works if your installation exposes Compose v2 under that command name.

```sh
docker compose logs -f picologger
docker compose ps -a
docker compose down
```

The one-shot `influxdb-init` service finishing with `Exited (0)` is normal.
InfluxDB and the logger use `restart: unless-stopped` and resume when Docker
starts after a reboot. Driver errors cause the logger to restart; pending
uploads survive restarts. Firmware initialization can delay the first reading.

## InfluxDB source build and Raspberry Pi page sizes

Both `influxdb` and `influxdb-init` build from `influxdb/Dockerfile`. The
multi-stage build compiles **InfluxDB 3.11.5** from its pinned upstream release
commit using Rust 1.97.1, then copies the binary into Debian Bookworm slim.
Docker builds for the host architecture, including ARM64 on a 64-bit Pi.

Build directly on the Pi that will run the database. Containers share the
host kernel, so jemalloc detects that kernel's page size during compilation;
no page-size overrides are applied. InfluxDB's default features are retained.
Python runtime libraries and `curl` are included for the processing engine
and health check.

If the kernel page size changes, rebuild with
`docker compose build --no-cache influxdb influxdb-init` before starting the
stack. Do not reuse an image built on a host with a different page size.

The first Rust build is substantial: allow plenty of time, disk space, and
RAM/swap, especially on a Pi. It uses two build jobs and disables release LTO
to reduce peak memory. Set `INFLUXDB_BUILD_JOBS=1` in `.env` to reduce parallel
compilation further. Build layers, Cargo downloads, and architecture-specific
compilation artifacts are cached for reuse.

To switch an existing installation to the source-built containers:

```sh
docker compose up -d --build
```

The data paths, node ID, and InfluxDB UID/GID (1500) match the previous image,
so existing database and token volumes can be reused.

## Configure probes

Defaults: **channels 1–8, all type T, every 5 seconds, 50 Hz mains rejection**.
CJC is always recorded. To select connected probes or change their types, copy
the optional configuration and edit it:

```sh
cp .env.example .env
```

For example, only the original type-T probe on channel 5:

```dotenv
TC08_CHANNELS=5:T
TC08_INTERVAL=5
TC08_MAINS=50
INFLUXDB_DATABASE=picolog
```

Mixed types are supported, for example `TC08_CHANNELS=1:K,2:K,5:T`. Supported
types are B, E, J, K, N, R, S, T. Unspecified channels are disabled. The actual
interval is at least the SDK's minimum conversion interval. `TC08_DEVICE_ID`
optionally overrides the device's batch/serial identifier.

Apply configuration changes with `docker compose up -d`. After editing Python
code or the Dockerfile, run `docker compose up -d --build`.

## Explorer web UI

Compose also starts **InfluxDB 3 Explorer 1.9.0** (`influxdata/influxdb3-ui`)
in admin mode. Open **http://localhost:8080** on the Docker host to query,
visualize, and manage the database. The `Pico TC-08` server connection is
automatically configured with `http://influxdb:8181`, the selected database,
and the same token used by the logger.

Explorer is a separate container because this stack uses **InfluxDB 3 Core**.
The bundled Explorer introduced in version 3.11 applies to **Enterprise**.

For access from another machine on your LAN, set `EXPLORER_BIND_ADDRESS=0.0.0.0`
in `.env`, run `docker compose up -d`, then visit `http://<pi-address>:8080`.
`EXPLORER_PORT` can change the host port. The UI has admin access through the
configured token, so expose it only to users who should have that access.

Explorer saves its settings and session key in `explorer-data`. Connection
defaults for new browser sessions are generated in `explorer-config`; existing
connections can be edited through the UI if you later change the database or token.

```sh
docker compose logs -f explorer
```

## Query readings

The query helper uses the shared token automatically:

```sh
docker compose exec picologger python3 query.py
docker compose exec picologger python3 query.py \
  "SELECT * FROM tc08 WHERE time >= now() - INTERVAL '1 hour' AND channel = '5' AND valid = true ORDER BY time DESC LIMIT 20"
```

If the logger is stopped, use `docker compose run --rm --no-deps picologger
python3 query.py`. This helper does not open the USB device.

The HTTP API is also available at `http://localhost:8181` on the Docker host.
For external clients, retrieve the generated token explicitly:

```sh
docker compose exec picologger python3 -c 'from influx_config import load_token; print(load_token())'
```

Use that value as a Bearer token. InfluxDB's health endpoint is unauthenticated
for the container health check; data APIs require authentication.

## Data and persistence

Table `tc08` contains one row per enabled input plus CJC for each acquisition:

| Column | Meaning |
|---|---|
| `time` | Shared UTC timestamp at the end of the SDK read |
| `device` | Unit batch/serial or configured device ID (tag) |
| `channel` | `0` for CJC, `1`–`8` for inputs (tag) |
| `thermocouple_type` | Configured type, or `CJC` (tag) |
| `temperature_c` | Returned temperature in Celsius |
| `overflow_flags` | Complete SDK overflow bit mask |
| `valid` | False for overflow or a non-finite temperature |

Overflow readings retain the returned temperature. Non-finite readings retain
their status without a temperature field. Filter on `valid = true` for analysis.

Compose manages five named volumes:

- `influxdb-data`: database catalog, write-ahead log, and temperature data.
- `influxdb-auth`: generated token, reused across restarts.
- `logger-data`: durable SQLite upload queue at `/data/picolog.sqlite3`.
- `explorer-config`: generated initial Explorer connection configuration.
- `explorer-data`: Explorer settings and application database.

Every sample is committed to SQLite before a background thread uploads it.
Failed uploads are retried without blocking acquisition; acknowledged samples
are removed. Replays retain their original timestamps to avoid duplicate rows.
The queue grows during database outages, so monitor disk space and upload logs.
Keep the same database destination for a queue containing pending readings.

`docker compose down` preserves the volumes. **`docker compose down -v` deletes
the temperatures, token, pending readings, and Explorer settings.** Back up the
volumes together. Keep the Compose project name/directory name stable to reuse them.

InfluxDB 3 Core limits each query's time range to approximately 72 hours; use
bounded time windows when querying history.

## USB access

The logger uses the official `libusbtc08 2.0.151-1r6217` package, downloaded
from Pico and SHA-256 verified for the image's native AMD64/ARM64 architecture.
It runs as root inside its container, binds `/dev/bus/usb`, and permits USB
character devices (major 189). Binding the bus directory allows firmware
re-enumeration and hotplug without fixing a particular USB device number.

The wrapper opens the first available TC-08. Run only one reader for that unit;
stop `picologger` before running SDK diagnostics. For USB errors, check the
connection with `lsusb`, the container logs, and whether another process owns
the device. Docker Desktop USB forwarding and rootless Docker are not covered
by this configuration.

## Existing host-only installation

Stop any host logger/systemd service before starting the containerized logger.
The existing `influxdb-data` volume and node ID are retained. If you previously
created an admin token manually, keep `INFLUXDB_TOKEN=your-existing-token` in
`.env`; it overrides the generated token for the logger and query helper.
InfluxDB does not replace an existing admin token with an offline token.

If you have pending samples in a host `data/picolog.sqlite3`, stop the host
logger and copy that database into `logger-data` before starting acquisition.
Include its SQLite WAL if present, or checkpoint the database first. The
previous host queue is not automatically imported.

## Development and tests

```text
compose.yaml              Database, token initialization, and USB logger
influxdb/                 Source-built InfluxDB Dockerfile
deploy/init-influxdb.sh    Idempotent token generation
deploy/start-explorer.sh   Explorer IPv4 startup and persistent session key
picologger/               Dockerfile, Python code, diagnostics, tests
tools/                    Optional USB tracing source and GDB script
local-artifacts/          Ignored local driver binaries and captured traces
```

Run tests in the built logger image; these do not access USB hardware by default:

```sh
docker compose run --rm --no-deps picologger python3 -m unittest discover -v
# Also test real database writes, queries, deduplication and authentication:
docker compose run --rm --no-deps -e INFLUXDB_INTEGRATION=1 \
  picologger python3 -m unittest -v test_influxdb
```

The live test creates a separate `picolog_test_<timestamp>` database containing
synthetic readings. Host-only tests can run with `python3 -m unittest discover
-s picologger -v`; the SDK library test needs a local Pico driver.

See [SDK and raw USB diagnostics](picologger/README.md) and
[protocol notes](picologger/PROTOCOL.md) for hardware details.
