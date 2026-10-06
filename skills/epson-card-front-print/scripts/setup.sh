#!/bin/bash
set -euo pipefail
skill_root="$(cd "$(dirname "$0")/.." && pwd)"
venv_path="$HOME/.cache/epson-card-front-print/venv"
base_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [ ! -x "$base_python" ]; then base_python="$(command -v python3)"; fi
if command -v uv >/dev/null; then
  if [ ! -x "$venv_path/bin/python" ]; then uv venv --python "$base_python" "$venv_path"; fi
  uv pip install --python "$venv_path/bin/python" -r "$skill_root/requirements-tested.txt"
else
  if [ ! -x "$venv_path/bin/python" ]; then "$base_python" -m venv "$venv_path"; fi
  "$venv_path/bin/python" -m pip install -r "$skill_root/requirements-tested.txt"
fi
