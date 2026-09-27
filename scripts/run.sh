#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [ -n "${EPSON_PVC_PYTHON:-}" ]; then
  exec "$EPSON_PVC_PYTHON" "$root/scripts/cardprint.py" "$@"
fi
venv_python="$root/venv/bin/python"
if [ -x "$venv_python" ]; then exec "$venv_python" "$root/scripts/cardprint.py" "$@"; fi
exec python3 "$root/scripts/cardprint.py" "$@"
