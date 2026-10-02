#!/usr/bin/env bash
# Quadwright setup for macOS / Linux / WSL.
# Usage: ./scripts/setup.sh [--ml]
set -euo pipefail

cd "$(dirname "$0")/.."
EXTRAS="dev"
if [[ "${1:-}" == "--ml" ]]; then EXTRAS="dev,ml"; fi

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }

step "Finding Python 3.11+"
PY=""
for candidate in python3.12 python3.13 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$candidate"; break
  fi
done
if [[ -z "$PY" ]]; then
  echo "Python 3.11 or newer is required: https://www.python.org/downloads/" >&2
  exit 1
fi
echo "Using $($PY --version)"

step "Creating virtual environment (.venv)"
[[ -d .venv ]] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip --quiet

step "Installing Quadwright [$EXTRAS] (first run can take a few minutes)"
pip install -e ".[$EXTRAS]"

step "Creating local data folders"
mkdir -p data/raw data/interim outputs

step "Setting up git"
if ! command -v git >/dev/null 2>&1; then
  warn "git not found; install it from https://git-scm.com and re-run."
else
  if [[ ! -d .git ]]; then git init -b main >/dev/null; echo "Initialized git repo on branch main"; fi
  pre-commit install >/dev/null && echo "pre-commit hooks installed"
fi

step "Checking: lint, tests, example config"
ruff check .
ruff format --check . || warn "Formatting differs; run: ruff format ."
pytest
quadwright validate configs/campuses/example-university.yaml

step "Optional tools"
if command -v npx >/dev/null 2>&1; then
  echo "Node.js found. Measure token usage any time with: npx ccusage@latest daily"
else
  warn "Node.js not found. Install it later for ccusage, Ponytail, and Context7: https://nodejs.org"
fi
command -v pyright-langserver >/dev/null 2>&1 && echo "pyright-langserver ready for the pyright-lsp plugin"

cat <<'MSG'

Setup complete.
Next:
  1. Activate the environment in new terminals:  source .venv/bin/activate
  2. Make your first commit and push (docs/SETUP.md, step 2)
  3. Install the Claude Code plugins (docs/SETUP.md, step 3)
MSG
