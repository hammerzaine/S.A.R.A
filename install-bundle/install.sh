#!/usr/bin/env bash
# S.A.R.A installer — Linux & macOS
# Run from the S.A.R.A repo root:  bash install-bundle/install.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="${PYTHON:-python3}"
echo "== S.A.R.A installer =="
echo "   repo : $REPO_ROOT"
echo "   python: $($PY --version 2>&1)"

# 1) Create a local virtualenv (avoids touching system Python; works on
#    macOS where system Python is locked down, and Linux where it varies).
VENV="$REPO_ROOT/.venv"
if [ ! -d "$VENV" ]; then
  echo "== creating virtualenv =="
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# 2) Install dependencies
echo "== installing dependencies =="
pip install --upgrade pip >/dev/null
pip install -r install-bundle/requirements.txt

# 3) Convenience launcher on PATH (optional)
BIN="$REPO_ROOT/bin/sara"
mkdir -p "$REPO_ROOT/bin"
cat > "$BIN" <<'EOF'
#!/usr/bin/env bash
# S.A.R.A launcher — activates the venv and runs the unified entry point.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$HERE/.venv/bin/activate"
exec python "$HERE/sara.py" "$@"
EOF
chmod +x "$BIN"

echo ""
echo "== DONE =="
echo "Run the agent:"
echo "  $BIN                 # interactive CLI"
echo "  $BIN 'your question' # one-shot"
echo "  $BIN web             # web UI at http://localhost:8800"
echo ""
echo "NOTE: S.A.R.A defaults to Nous Portal + stepfun/step-3.7-flash:free."
echo "      Edit config.json -> base_url / model / provider, or use /status."
