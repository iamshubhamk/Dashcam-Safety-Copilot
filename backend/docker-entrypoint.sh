#!/bin/sh
# Starts as root only to make the bind-mounted storage folder writable (on Linux hosts a fresh
# ./data/storage is created root-owned), then drops to the unprivileged `app` user.
set -e
if [ "$(id -u)" = "0" ]; then
    mkdir -p "${DASHCAM_STORAGE_DIR:-/data/storage}" "${DASHCAM_WORK_DIR:-/data/work}"
    chown app:app "${DASHCAM_STORAGE_DIR:-/data/storage}" "${DASHCAM_WORK_DIR:-/data/work}"
    exec setpriv --reuid=app --regid=app --init-groups "$@"
fi
exec "$@"
