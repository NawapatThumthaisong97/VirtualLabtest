# syntax=docker/dockerfile:1

FROM python:3.12-slim

# curl ใช้ทำ healthcheck ใน compose — ไม่ได้มีติดมากับ slim image
# libpq5 เป็น runtime lib ที่ psycopg2-binary ต้องใช้
#
# ที่เหลือเป็นของที่ SkyPilot เรียกผ่าน subprocess ตอนใช้ Kubernetes เป็น backend
# ลง pip install skypilot อย่างเดียวไม่พอ เพราะมันไม่ได้ลากพวกนี้มาให้
#   netcat-openbsd - ให้คำสั่ง nc ที่ SkyPilot ใช้ทำ portforward (networking mode
#                    เริ่มต้นของ Kubernetes) ขาดตัวนี้ sky check จะขึ้น disabled
#   socat          - port-forward เข้า pod
#   openssh-client - ssh + ssh-keygen สำหรับ key ที่ SkyPilot สร้างเอง
#   rsync          - ส่งไฟล์ workdir เข้า pod
#   git            - SkyPilot เรียกตอน launch (sky check ไม่ได้ตรวจตัวนี้ให้
#                    ต้องเปิด SKYPILOT_DEBUG=1 ถึงจะเห็นว่าเป็น git ที่หาย)
# ขาดตัวไหนไปจะได้ FileNotFoundError ตอนสร้าง session ซึ่งอ่านแล้วนึกว่าไฟล์หาย
# ทั้งที่เป็นตัวโปรแกรมเองที่ไม่มี — เช็คว่าขาดอะไรได้ด้วย `sky check kubernetes`
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl libpq5 socat openssh-client rsync netcat-openbsd git \
    && rm -rf /var/lib/apt/lists/*

# kubectl ไม่มีใน apt ของ debian ต้องโหลด binary ตรง
# ปล่อยว่างไว้จะใช้ stable ล่าสุด หรือ pin ด้วย --build-arg KUBECTL_VERSION=v1.35.5
# ควรอยู่ใน ±1 minor version กับ k3s ที่ cluster ใช้
ARG KUBECTL_VERSION=""
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    ver="${KUBECTL_VERSION:-$(curl -fsSL https://dl.k8s.io/release/stable.txt)}"; \
    curl -fsSL -o /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${ver}/bin/linux/${arch}/kubectl"; \
    chmod +x /usr/local/bin/kubectl; \
    kubectl version --client

WORKDIR /app

# copy requirement ก่อน source เพื่อให้ layer นี้ cache ไว้ได้
# แก้โค้ดแล้วไม่ต้อง pip install ใหม่ทุกรอบ
COPY requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

COPY app/ ./app/

# script/ ต้องติดไปด้วย ไม่ใช่แค่ app/ — init_db.py สร้างตาราง, run_seed.py
# ใส่ข้อมูลตั้งต้น, setup_lab_doc.py ผูกไฟล์เอกสารเข้ากับ lab และ assets/
# เก็บ PDF ต้นฉบับไว้ ทั้งหมดจำเป็นตอนตั้งเครื่องใหม่
COPY script/ ./script/

# storage เป็นที่เก็บไฟล์เอกสารแลป (STORAGE_ROOT ใน settings)
# สร้างไว้เผื่อกรณีที่ยังไม่มี volume mount ทับ
RUN mkdir -p /app/storage

EXPOSE 8000

# ไม่ใส่ --reload เพราะเป็น production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
