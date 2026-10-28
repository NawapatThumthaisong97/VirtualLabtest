FROM python:3.12-slim

# sqlite3 = CLI shell สำหรับ poke /data/library.db, curl/gnupg/ca-certificates = ใช้ติดตั้ง
# node.js (NodeSource script) กับ code-server (official install script) ต่อด้านล่าง
RUN apt-get update && apt-get install -y --no-install-recommends \
      sqlite3 curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# code-server (ide) — ติดตั้งตัว binary ตรง ๆ ไม่ใช้ image codercom/code-server แยกแล้ว
# เพราะทุกอย่างต้องอยู่ใน container เดียวกันหมด
RUN curl -fsSL https://code-server.dev/install.sh | sh

# python deps ของ server (เดิมอยู่ใน server/Dockerfile)
RUN pip install --no-cache-dir flask flask-cors gunicorn

WORKDIR /app

# --- server: bake โค้ด + seed เพลงจริงเหมือน server/Dockerfile เดิม ---
COPY server/ /app/server/
ENV DATA_DIR=/data
ENV MUSIC_DIR=/data/music
RUN mkdir -p /data/music \
    && cp /app/server/music/love_story.wav /data/music/love_story.wav \
    && cd /app/server && python musicgen.py && python -c "import server"

# --- client: npm install ก่อนแยกจาก COPY โค้ด ให้ cache layer ตอน build ซ้ำเร็วขึ้น ---
COPY client/package*.json /app/client/
RUN cd /app/client && npm install
COPY client/ /app/client/

# --- ide: settings.json เดิม, เปิด /app ตรง ๆ (มีทั้ง server/ กับ client/ ให้แก้ในตัวเดียว) ---
RUN mkdir -p /root/.local/share/code-server/User
COPY ide/settings.json /root/.local/share/code-server/User/settings.json

COPY skypilot/run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8080 5173 8443
CMD ["/run.sh"]
