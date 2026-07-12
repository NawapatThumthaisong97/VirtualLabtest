#!/bin/sh
set -e

WORKSPACE=/workspace/client

# seed the shared volume from the image's baked-in source on first run only -
# never overwrite a workspace that already has student edits in it
if [ ! -f "$WORKSPACE/package.json" ]; then
  echo "[entrypoint] seeding $WORKSPACE from image"
  mkdir -p "$WORKSPACE"
  cp -r /app/. "$WORKSPACE/"
  # this container runs as root, but code-server (ide) edits these same files as uid 1000
  # (its default "coder" user) - without this, root-owned files aren't writable there
  chown -R 1000:1000 "$WORKSPACE"
fi

cd "$WORKSPACE"
exec "$@"
