#!/usr/bin/env bash
# make-dist.sh — build a clean, shippable S.A.R.A distribution.
#
# Strips everything learned at chat-time so the shipped agent starts blank:
#   * skills table      -> not shipped (agent creates an empty DB on first run)
#   * facts/memory      -> not shipped
#   * turns/history     -> not shipped
#   * SOUL.md           -> shipped BLANK (personality is re-learned or set by you)
#   * config/creds/DB   -> never shipped (git-ignored; defaults used if absent)
#
# What IS kept (hardcoded in code, not learned):
#   * all tools in sara/tools.py (ConfigTool, ModelList, UpgradeTool, ...)
#   * the PROTOCOL / operating rules hardcoded in sara/agent.py
#   * the full agent core + CLI + webapp + install bundle
#
# Usage:  bash make-dist.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$HERE/dist-clean"
SRC="$HERE"

echo "== building clean dist at $DIST =="

# 1) wipe any previous build
rm -rf "$DIST"
mkdir -p "$DIST"

# 2) copy tracked files (git archive == exactly what's committed, no secrets)
git -C "$SRC" archive --format=tar HEAD | tar -x -C "$DIST"

# 3) copy the unified launcher (not yet committed -> add manually)
[ -f "$SRC/sara.py" ] && cp "$SRC/sara.py" "$DIST/sara.py"

# 4) copy the install bundle (not committed -> add manually)
[ -d "$SRC/install-bundle" ] && cp -r "$SRC/install-bundle" "$DIST/install-bundle"

# 5) blank SOUL.md (personality ships empty; set your own or let her learn)
: > "$DIST/SOUL.md"

# 6) empty data/ dir, NO sara.db (agent creates a blank one on first boot)
mkdir -p "$DIST/data"
rm -f "$DIST/data/sara.db"

# 7) ensure a .gitignore exists in the dist so end-users don't commit secrets
cat > "$DIST/.gitignore" <<'EOF'
# Local state / secrets — never commit
credentials.json
config.json
upgrade_state.json
data/
backups/
__pycache__/
*.pyc
*.bak*
EOF

echo "== done. dist tree: =="
find "$DIST" -type f -not -path "*/__pycache__/*" | sort | sed 's#^#  #'
echo ""
echo "SOUL.md bytes : $(wc -c < "$DIST/SOUL.md")  (want 0 = blank)"
echo "data/ files  : $(ls -A "$DIST/data" 2>/dev/null | wc -l)  (want 0 = no DB shipped)"
