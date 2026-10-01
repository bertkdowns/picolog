FROM python:3.12-slim-bookworm

# The official SDK includes the TC-08 firmware loader. Pin and verify both
# native packages instead of copying a host-specific library into the image.
RUN set -eux; \
    architecture="$(dpkg --print-architecture)"; \
    case "$architecture" in \
      amd64) checksum=164c92be12b7894cce4c86d528f2b0906f4ec0d762995278ebc5a2a2bb707466 ;; \
      arm64) checksum=26c85ce1365064164002ec6d0e5edcdd2b5a36cdde61c000c9bf55b27309ed27 ;; \
      *) echo "Unsupported architecture: $architecture" >&2; exit 1 ;; \
    esac; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    curl --fail --location --retry 3 \
      "https://labs.picotech.com/picoscope7/debian/pool/main/libu/libusbtc08/libusbtc08_2.0.151-1r6217_${architecture}.deb" \
      --output /tmp/libusbtc08.deb; \
    printf '%s  /tmp/libusbtc08.deb\n' "$checksum" | sha256sum --check -; \
    apt-get install -y --no-install-recommends /tmp/libusbtc08.deb; \
    rm -f /tmp/libusbtc08.deb; \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    USBTC08_LIBRARY=/opt/picoscope/lib/libusbtc08.so.2.0.0
WORKDIR /app
COPY *.py ./
CMD ["python3", "log_influxdb.py", "--spool", "/data/picolog.sqlite3"]
