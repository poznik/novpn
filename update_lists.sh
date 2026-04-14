#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "Python not found. Install python3 or python." >&2
    exit 1
fi

echo "Using Python: $PYTHON_BIN"
echo "Project root: $ROOT_DIR"

if [[ -d "$ROOT_DIR/bats" ]]; then
    echo
    echo "[1/2] Rebuilding foreign lists from bats/*.bat"
    "$PYTHON_BIN" "$ROOT_DIR/scripts/build_services.py"
else
    echo
    echo "[1/2] Skipping build_services.py: bats/ directory not found"
fi

echo
echo "[2/2] Refreshing Russian lists from live DNS and RIPEstat"
"$PYTHON_BIN" "$ROOT_DIR/scripts/check_ru_services.py"

echo
echo "List update completed."
