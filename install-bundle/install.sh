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

# 0) Verify/bootstrap core files so installs from dist/clean copies don’t break.
CORE_OK=true
[ -f "$REPO_ROOT/sara.py" ] || CORE_OK=false
[ -d "$REPO_ROOT/sara" ] || CORE_OK=false
[ -d "$REPO_ROOT/web" ] || CORE_OK=false

if [ "$CORE_OK" = false ]; then
  echo "== checking for S.A.R.A source bundle =="
  CANDIDATE=""
  for CAND in \
    "$REPO_ROOT/install-bundle/src" \
    "$HOME/SARA" \
    "$HOME/sara" \
    "$REPO_ROOT/.upgrade_tmp" \
    "$REPO_ROOT/dist-clean" \
    "$REPO_ROOT/../SARA" \
    "$REPO_ROOT/../sara" \
    /srv/SARA \
    /srv/sara \
    /opt/SARA \
    /opt/sara
  do
    if [ -f "$CAND/sara.py" ] && [ -d "$CAND/sara" ] && [ -d "$CAND/web" ]; then
      CANDIDATE="$CAND"
      break
    fi
  done

  if [ -n "$CANDIDATE" ]; then
    echo "   source bundle found: $CANDIDATE"
    mkdir -p "$REPO_ROOT"
    # Copy the COMPLETE bundle: every top-level .py launcher/module plus the
    # sara/ package and web/ assets. sara.py is a launcher that imports
    # sara_cli, web, sara_upgrade, etc. as siblings — so we ship all of them.
    rm -rf "$REPO_ROOT/sara" "$REPO_ROOT/web" 2>/dev/null || true
    cp -r "$CANDIDATE/." "$REPO_ROOT/"
    echo "   core files restored from: $CANDIDATE"
  else
    echo "❌ sara.py (the actual entry point – MISSING)"
    echo "❌ sara/ (the core agent package – MISSING)"
    echo "❌ web/ (the UI assets – MISSING)"
    echo ""
    echo "No local S.A.R.A source bundle was found."
    echo "Checked: install-bundle/src, ~/SARA, ~/sara, .upgrade_tmp, dist-clean,"
    echo "         ../SARA, ../sara, /srv/SARA, /srv/sara, /opt/SARA, /opt/sara"
    echo ""
    echo "Fix: place or clone the S.A.R.A repo into one of those paths,"
    echo "     then rerun this installer."
    exit 1
  fi
fi

echo "✅ install-bundle/ (the installer scripts)"
echo "✅ requirements.txt (the dependencies)"
echo "✅ sara.py (the actual entry point)"
echo "✅ sara/ (the core agent package)"
echo "✅ web/ (the UI assets)"

# 1) Make sure the system can build a working venv. On a fresh Debian/Ubuntu the
#    python3-venv package is missing, so `python -m venv` creates a broken env
#    with no pip/activate (ensurepip fails inside it). Detect that BEFORE creating
#    the venv and self-heal by installing the right distro package.
#
# Note: `python -m venv --help` SUCCEEDS even when ensurepip is broken, so we
# probe ensurepip directly instead.
ensurepip_ok() { "$PY" -m ensurepip --version >/dev/null 2>&1; }

# Self-heal: if ensurepip is missing, install the distro venv package, then
# RE-PROBE — sudo may have just installed it. Repeat once.
if ! ensurepip_ok; then
  echo "== ensurepip missing — attempting to install system venv package =="
  PYVER="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  if command -v apt-get >/dev/null 2>&1; then
    echo "   apt-get install -y python${PYVER}-venv python3-pip"
    sudo apt-get update -y >/dev/null 2>&1 || true
    sudo apt-get install -y "python${PYVER}-venv" python3-pip >/dev/null 2>&1 || true
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y "python${PYVER}-devel" python3-pip >/dev/null 2>&1 || true
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add --no-cache "python${PYVER}-venv" py3-pip >/dev/null 2>&1 || true
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm "python-virtualenv" >/dev/null 2>&1 || true
  fi
  # Re-probe; if still missing, warn but keep going (get-pip fallback below).
  if ! ensurepip_ok; then
    echo "   ⚠ ensurepip still unavailable after package install (need sudo?)."
    echo "     Will try get-pip.py bootstrap as a fallback."
  fi
fi

# 1b) Create a local virtualenv (avoids touching system Python; works on
#    macOS where system Python is locked down, and Linux where it varies).
#
# A venv is "complete" only if it has python AND activate AND pip. A prior
# failed run can leave a half-broken .venv (python only, no activate/pip) —
# we must detect that and rebuild it, not skip creation.
VENV="$REPO_ROOT/.venv"
venv_complete() { [ -x "$VENV/bin/python" ] && [ -f "$VENV/bin/activate" ] && { [ -x "$VENV/bin/pip" ] || [ -x "$VENV/bin/pip3" ]; }; }

if ! venv_complete; then
  # Wipe any half-broken venv so we start clean.
  [ -e "$VENV" ] && rm -rf "$VENV"
  echo "== creating virtualenv =="
  if "$PY" -m venv "$VENV" 2>/dev/null && venv_complete; then
    : # normal path worked
  else
    echo "   venv ensurepip failed; trying --without-pip + get-pip bootstrap"
    rm -rf "$VENV"
    "$PY" -m venv --without-pip "$VENV" 2>/dev/null || true
    if [ -x "$VENV/bin/python" ] && { [ ! -x "$VENV/bin/pip" ] && [ ! -x "$VENV/bin/pip3" ]; }; then
      GETPIP="$(mktemp)"
      if curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$GETPIP" 2>/dev/null; then
        "$VENV/bin/python" "$GETPIP" >/dev/null 2>&1 || true
      fi
      rm -f "$GETPIP"
    fi
  fi
fi

# Guard: if the venv still isn't complete, bail with a clear message.
if ! venv_complete; then
  echo "❌ could not create a working Python virtualenv."
  echo "   On Debian/Ubuntu run:  sudo apt install python${PYVER}-venv python3-pip"
  echo "   Then rerun:  bash install-bundle/install.sh"
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# 2) Install dependencies
echo "== installing dependencies =="
pip install --upgrade pip >/dev/null 2>&1 || true
pip install -r install-bundle/requirements.txt

# 3) Convenience launcher on PATH (optional)
BIN="$REPO_ROOT/bin/sara"
mkdir -p "$REPO_ROOT/bin"
cat > "$BIN" <<'EOF'
#!/usr/bin/env bash
# S.A.R.A launcher — activates the venv and runs the unified entry point.
# Resolve the REAL script location (handles being called via a symlink in
# ~/.local/bin), so HERE always points at the repo root, never the symlink dir.
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
HERE="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
source "$HERE/.venv/bin/activate"
exec python3 "$HERE/sara.py" "$@"
EOF
chmod +x "$BIN"

# 3b) Symlink into ~/.local/bin so `sara` works without typing the full path,
#    and make sure ~/.local/bin is actually ON the PATH (it isn't by default on
#    minimal Ubuntu). Auto-append it to the shell rc files so `sara` just works
#    after a fresh login — no manual step required.
LOCALBIN="$HOME/.local/bin"
if [ -d "$LOCALBIN" ] || mkdir -p "$LOCALBIN" 2>/dev/null; then
  ln -sf "$BIN" "$LOCALBIN/sara" 2>/dev/null && chmod +x "$LOCALBIN/sara" 2>/dev/null
  case ":$PATH:" in
    *":$LOCALBIN:"*) ;;
    *)
      # Append to the user's shell rc files so future logins pick it up.
      # Patch .bashrc (interactive) and .profile (login) — and create .profile
      # if it doesn't exist, so login shells always get the PATH.
      for RC in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zshrc"; do
        touch "$RC" 2>/dev/null || true
        grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$RC" 2>/dev/null || \
          echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
      done
      # Also export it for THIS session so `sara` works immediately.
      export PATH="$LOCALBIN:$PATH"
      echo "   ✓ added ~/.local/bin to PATH (sara works in new shells + this session)" ;;
  esac
fi

echo ""
echo "== DONE =="
echo "Run the agent:"
echo "  $BIN                 # interactive CLI"
echo "  $BIN 'your question' # one-shot"
echo "  $BIN web             # web UI at http://localhost:8800"
echo "  sara                 # if ~/.local/bin is on PATH"
echo ""
echo "NOTE: S.A.R.A defaults to Nous Portal + stepfun/step-3.7-flash:free."
echo "      Edit config.json -> base_url / model / provider, or use /status."
