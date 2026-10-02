#!/usr/bin/env bash
# Run the same checks as CI. Usage: ./scripts/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -d .venv ]] && source .venv/bin/activate
ruff check .
ruff format --check .
pytest
quadwright validate configs/campuses/example-university.yaml
echo "All checks passed."
