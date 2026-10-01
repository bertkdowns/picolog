#!/bin/sh
set -eu

# This volume is initialized with the InfluxDB image's directory ownership.
# Generate only once and publish atomically, without logging the credential.
umask 077
directory=/var/lib/influxdb3/auth
mkdir -p "$directory"
if [ ! -s "$directory/admin-token.json" ]; then
    influxdb3 create token --admin --offline \
        --output-file "$directory/admin-token.json.tmp" >/dev/null
    mv "$directory/admin-token.json.tmp" "$directory/admin-token.json"
fi
