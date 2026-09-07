# syntax=docker/dockerfile:1

FROM python:3.12-slim

# curl ใช้ทำ healthcheck ใน compose — ไม่ได้มีติดมากับ slim image
# libpq5 เป็น runtime lib ที่ psycopg2-binary ต้องใช้
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy requirement ก่อน source เพื่อให้ layer นี้ cache ไว้ได้
# แก้โค้ดแล้วไม่ต้อง pip install ใหม่ทุกรอบ
COPY requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

COPY app/ ./app/

# storage เป็นที่เก็บไฟล์เอกสารแลป (STORAGE_ROOT ใน settings)
# สร้างไว้เผื่อกรณีที่ยังไม่มี volume mount ทับ
RUN mkdir -p /app/storage

EXPOSE 8000

# ไม่ใส่ --reload เพราะเป็น production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
