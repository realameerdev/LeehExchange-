#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Keep post-merge setup non-interactive and safe to repeat. The project uses
# the Replit-managed Python environment, so dependency installation is only
# needed when the lockfile changes; compilation is always a fast sanity check.
if [[ -f uv.lock && -f pyproject.toml ]]; then
  uv sync --frozen --no-dev
fi

python -m py_compile app.py telegram_bot.py handlers.py services.py utils.py