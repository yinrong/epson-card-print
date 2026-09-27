#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
venv_path="$root/venv"
if command -v uv >/dev/null; then
  [ -x "$venv_path/bin/python" ] || uv venv "$venv_path"
  uv pip install --python "$venv_path/bin/python" -r "$root/requirements-tested.txt"
else
  [ -x "$venv_path/bin/python" ] || python3 -m venv "$venv_path"
  "$venv_path/bin/python" -m pip install -r "$root/requirements-tested.txt"
fi
echo "done: $venv_path/bin/python"
