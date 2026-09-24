#!/usr/bin/env bash
# Nightly: caption new TikToks and label everything new, writing to the droplet's DB.
set -u
exec >>"$HOME/am-nightly.log" 2>&1
echo "=== $(date) start"
cd "$HOME/projects/algorithm-mirror/server" || exit 1
source .venv/bin/activate
pkill -f "5433:localhost:5432" 2>/dev/null
ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -f -N -L 5433:localhost:5432 root@198.199.64.41 \
  || { echo "tunnel failed"; exit 1; }
export DATABASE_URL="postgresql://mirror@localhost:5433/algorithm_mirror"  # password from ~/.pgpass
python enrich_tiktok.py
python label_v3.py
pkill -f "5433:localhost:5432"
echo "=== $(date) done"
