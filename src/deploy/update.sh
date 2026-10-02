#!/usr/bin/env bash
# Change the app on a running host without replacing it: check out a ref of this repository,
# rebuild the app's image, and restart only the app's container. The models keep running.
#   ssh root@<host> bash /opt/sys1/src/deploy/update.sh <branch, tag or commit>
# A new repo_ref in Terraform would instead replace the whole host: a new address, a fresh
# bring-up and a fresh request for GPU capacity.
set -euo pipefail

ref=${1:?usage: update.sh <branch, tag or commit>}
repo=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
say() { echo "$(date -u +%FT%TZ) sys1: $*"; }
# Every compose call reads the settings file, as compose.yaml requires.
compose() { docker compose --env-file /etc/sys1.env -f "$repo/src/deploy/compose.yaml" "$@"; }

say "update: fetch $ref"
git -C "$repo" fetch --tags --prune origin
# A branch moves, so take the remote's newest commit of it; a tag or a commit is taken as it is.
if git -C "$repo" rev-parse --verify --quiet "refs/remotes/origin/$ref" >/dev/null; then
  target=origin/$ref
else
  target=$ref
fi
git -C "$repo" checkout --quiet --detach "$target"
say "update: now at $(git -C "$repo" log -1 --format='%h %s')"

say "update: rebuild the app's image"
compose build app
say "update: restart the app alone"
compose up -d --no-deps app
say "update: done; the model servers kept running"
