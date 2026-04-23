#!/usr/bin/env bash
# Git refresh (bind-mount mode).
# Runs from inside the app container via "docker exec msa-backup-app /app/scripts/refresh.sh",
# or from the host via the Dockge console.
# Safe on failure: uses --hard reset only after a successful fetch.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/app}"
BRANCH="${GIT_BRANCH:-main}"

cd "${REPO_DIR}"

echo "[refresh] git fetch..."
git fetch --all --prune

echo "[refresh] reset to origin/${BRANCH}..."
git reset --hard "origin/${BRANCH}"

echo "[refresh] pip install..."
pip install --no-cache-dir -r requirements.txt

if [ -d "/app/static" ]; then
  echo "[refresh] frontend already built at container build time; skipping npm."
fi

echo "[refresh] running migrations..."
alembic upgrade head || true

echo "[refresh] signalling reload via uvicorn SIGHUP is not supported — Dockge restart recommended."
echo "[refresh] DONE. Restart the 'app', 'worker' and 'beat' services in Dockge."
