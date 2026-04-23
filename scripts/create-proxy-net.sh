#!/usr/bin/env bash
# Creates (if missing) the shared Docker network used by npm-stack and backup-stack.
# Run ONCE per host, before bringing the stacks up in Dockge.
set -euo pipefail

NET_NAME="${PROXY_NETWORK_NAME:-proxy-net}"

if docker network inspect "${NET_NAME}" >/dev/null 2>&1; then
  echo "[create-proxy-net] network '${NET_NAME}' already exists — nothing to do."
  exit 0
fi

echo "[create-proxy-net] creating external bridge network '${NET_NAME}'..."
docker network create \
  --driver bridge \
  --attachable \
  "${NET_NAME}"
echo "[create-proxy-net] done."
