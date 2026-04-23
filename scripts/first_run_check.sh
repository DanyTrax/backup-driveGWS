#!/usr/bin/env bash
# Pre-flight check to run on the host BEFORE bringing Dockge stacks up.
# Validates: docker installed, proxy-net network exists, .env present, ports 80/443 free.
set -euo pipefail

c_red() { printf '\033[31m%s\033[0m\n' "$*"; }
c_grn() { printf '\033[32m%s\033[0m\n' "$*"; }
c_ylw() { printf '\033[33m%s\033[0m\n' "$*"; }

ok=1

echo "=== MSA Backup Commander — first run check ==="

command -v docker >/dev/null 2>&1 && c_grn "[ok] docker installed" || { c_red "[x] docker missing"; ok=0; }

if docker network inspect proxy-net >/dev/null 2>&1; then
  c_grn "[ok] proxy-net network exists"
else
  c_ylw "[!] proxy-net network missing — run: docker network create proxy-net"
  ok=0
fi

if [ -f .env ]; then
  c_grn "[ok] .env present"
else
  c_ylw "[!] .env missing — copy .env.example to .env and fill secrets"
  ok=0
fi

for p in 80 443; do
  if lsof -nP -iTCP:${p} -sTCP:LISTEN >/dev/null 2>&1; then
    c_ylw "[!] port ${p}/tcp is in use (expected if Mailcow or NPM already running)"
  else
    c_grn "[ok] port ${p}/tcp is free"
  fi
done

if [ "${ok}" = 1 ]; then
  c_grn "All pre-flight checks passed. You can bring up the stacks in Dockge."
  exit 0
fi
c_red "Fix the issues above and re-run."
exit 1
