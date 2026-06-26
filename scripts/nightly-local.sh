#!/bin/bash
# Run nightly learning pipeline locally and rebuild the site.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  source "$ROOT/.venv/bin/activate"
fi

pip install -q -r orchestrator/requirements.txt -r site/requirements.txt

if [[ -z "${CURSOR_API_KEY:-}" ]]; then
  if [[ " $* " == *" --dry-run "* ]]; then
    echo "CURSOR_API_KEY not set — running explicit dry-run"
    python orchestrator/nightly.py "$@" --force
  else
    echo "ERROR: CURSOR_API_KEY is not set." >&2
    echo "  Export CURSOR_API_KEY for a real run, or pass --dry-run for offline structure tests." >&2
    exit 1
  fi
else
  python orchestrator/nightly.py "$@" --force
fi

echo ""
echo "Start the site: python site/serve.py"
echo "  → http://127.0.0.1:8765/"
