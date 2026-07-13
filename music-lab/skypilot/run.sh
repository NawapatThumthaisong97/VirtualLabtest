#!/bin/bash
# รัน 3 process (server/client/ide) พร้อมกันในตัวเดียว ไม่มี Docker ซ้อน คุยกันผ่าน localhost
set -e

cd /app/server
DATA_DIR=/data MUSIC_DIR=/data/music flask --app server run --host=0.0.0.0 --port=8080 --debug &

cd /app/client
VITE_PROXY_TARGET=http://localhost:8080 npm run dev -- --host 0.0.0.0 --port 5173 &

PASSWORD="${IDE_PASSWORD:-musiclab}" code-server --bind-addr 0.0.0.0:8443 --auth password /app &

# ถ้า process ไหนตายไปเงียบ ๆ ให้ container หยุดทั้งตัวเลย (จะได้เห็นว่าพังจาก sky status)
wait -n
exit $?
