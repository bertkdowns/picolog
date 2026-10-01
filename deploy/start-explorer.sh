#!/bin/sh
set -eu

# Explorer's bundled nginx config assumes IPv6 is available. This stack
# publishes IPv4 ports, so avoid startup failure on IPv6-disabled hosts.
sed -i '/listen \[::\]:/d' /app-root/nginx.conf

# Preserve sessions when the container is recreated, using the data volume.
umask 077
if [ ! -s /db/session-secret ]; then
    openssl rand -hex 32 > /db/session-secret.tmp
    mv /db/session-secret.tmp /db/session-secret
fi
SESSION_SECRET_KEY=$(cat /db/session-secret)
export SESSION_SECRET_KEY

exec /app-root/entrypoint.sh "$@"
