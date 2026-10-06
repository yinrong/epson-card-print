#!/bin/bash
set -euo pipefail
skill_root="$(cd "$(dirname "$0")/.." && pwd)"
entry="cardfront.py"
if [ -n "${EPSON_CARD_FRONT_PYTHON:-}" ]; then
  exec "$EPSON_CARD_FRONT_PYTHON" "$skill_root/scripts/$entry" "$@"
fi
venv_python="$HOME/.cache/epson-card-front-print/venv/bin/python"
if [ -x "$venv_python" ]; then exec "$venv_python" "$skill_root/scripts/$entry" "$@"; fi
runtime_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [ -x "$runtime_python" ]; then
  exec "$runtime_python" "$skill_root/scripts/$entry" "$@"
fi
exec python3 "$skill_root/scripts/$entry" "$@"
