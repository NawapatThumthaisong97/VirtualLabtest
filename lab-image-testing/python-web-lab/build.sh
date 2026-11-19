#!/bin/bash
# Build the passed image and every failed variant, then save each one as dist/<name>.tar for upload.
# Usage: ./build.sh [name ...]   (no names = all; names: passed localhost-only exits-immediately unused-port no-command)
set -euo pipefail

cd "$(dirname "$0")"
repo=vlab-test/python-web-lab
mkdir -p dist

build() {
  local name=$1 context=$2
  echo "== $name"
  docker build --platform linux/amd64 -t "$repo:$name" "$context"
  docker save -o "dist/$name.tar" "$repo:$name"
  ls -lh "dist/$name.tar" | awk '{print "   " $5 "  " $9}'
}

targets=("$@")
[ ${#targets[@]} -gt 0 ] || targets=(passed localhost-only exits-immediately unused-port no-command)

for name in "${targets[@]}"; do
  if [ "$name" = passed ]; then
    build passed passed
  else
    [ -d "failed/$name" ] || { echo "unknown case: $name" >&2; exit 2; }
    docker image inspect "$repo:passed" >/dev/null 2>&1 || build passed passed
    build "$name" "failed/$name"
  fi
done
