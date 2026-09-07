# syntax=docker/dockerfile:1

# ---------- stage 1: build ----------
FROM node:22-alpine AS build

WORKDIR /app

# npm ci ต้องใช้ package-lock.json — ได้ build ที่ reproducible กว่า npm install
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_* ถูกฝังลงไฟล์ตอน build ไม่ใช่อ่านตอน runtime
# เปลี่ยนค่านี้ทีหลังต้อง rebuild image ใหม่เท่านั้น แก้ .env แล้ว restart ไม่พอ
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# ---------- stage 2: serve ----------
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
