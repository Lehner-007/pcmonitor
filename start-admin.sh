#!/usr/bin/env bash
set -e
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PCMONITOR_ADMIN_QUERY=1
exec "$PROJECT_DIR/start.sh" "$@"
