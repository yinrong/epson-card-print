#!/bin/bash
set -euo pipefail
skill_root="$(cd "$(dirname "$0")/.." && pwd)"
if [ -n "${EPSON_PRINT_CARD_PYTHON:-}" ]; then
  exec "$EPSON_PRINT_CARD_PYTHON" "$skill_root/scripts/epson-print-card" "$@"
fi
venv_python="$HOME/.cache/epson-print-card/venv/bin/python"
if [ -x "$venv_python" ]; then exec "$venv_python" "$skill_root/scripts/epson-print-card" "$@"; fi
runtime_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [ -x "$runtime_python" ]; then
  exec "$runtime_python" "$skill_root/scripts/epson-print-card" "$@"
fi
exec python3 "$skill_root/scripts/epson-print-card" "$@"
