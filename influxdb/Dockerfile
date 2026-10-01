# syntax=docker/dockerfile:1
FROM rust:1.97.1-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates clang cmake git libprotobuf-dev libssl-dev lld pkg-config \
    protobuf-compiler python3-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Keep the same database version as the previous prebuilt image. Verify the
# release commit as well as the tag rather than building a moving branch.
RUN git clone --depth 1 --branch v3.11.5 https://github.com/influxdata/influxdb.git /src \
    && test "$(git -C /src rev-parse HEAD)" = f083f73c92eaa87186d39c81bbd8afc3a3fd8d94
WORKDIR /src

ARG CARGO_BUILD_JOBS=2
ARG TARGETARCH
ENV CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS} \
    CARGO_PROFILE_RELEASE_LTO=false \
    PYO3_PYTHON=/usr/bin/python3 \
    RUSTUP_TOOLCHAIN=1.97.1 \
    RUSTFLAGS="--cfg tokio_unstable -C link-arg=-fuse-ld=lld -C force-frame-pointers=yes"

# Build natively on the runtime host so jemalloc detects its kernel page size.
# Do not force a page size or a different build platform.
# Limit parallelism and disable release LTO to reduce peak build memory on Pi.
# Keep native artifacts separate if the host's kernel page size changes.
RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=picolog-influxdb-target-${TARGETARCH},target=/src/target,sharing=locked \
    target_dir="/src/target/$(getconf PAGESIZE)" \
    && cargo build --locked --release --package influxdb3 --bin influxdb3 \
      --target-dir "$target_dir" \
    && install -Dm755 "$target_dir/release/influxdb3" /out/influxdb3

FROM debian:bookworm-slim

# Python is dynamically linked by InfluxDB's processing engine. curl is used
# by Compose's health check. Match the old image's UID/GID for existing volumes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libpython3.11 libssl3 libstdc++6 python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1500 influxdb3 \
    && useradd --uid 1500 --gid influxdb3 --create-home --shell /bin/bash influxdb3 \
    && mkdir -p /var/lib/influxdb3 /plugins /home/influxdb3/.influxdb3 \
    && chown -R influxdb3:influxdb3 /var/lib/influxdb3 /plugins /home/influxdb3

COPY --from=builder /out/influxdb3 /usr/local/bin/influxdb3
ENV HOME=/home/influxdb3 \
    INFLUXDB3_PLUGIN_DIR=/plugins
USER influxdb3
RUN influxdb3 --version
EXPOSE 8181
ENTRYPOINT ["influxdb3"]
CMD ["serve"]
