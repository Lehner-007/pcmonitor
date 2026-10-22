#!/usr/bin/env bash
set -e
TEMPLATE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$TEMPLATE_DIR"
export PYTHON_TEMPLATE_DEV=1
exec /usr/bin/python3 "$TEMPLATE_DIR/pcmonitor.py" "$@"
