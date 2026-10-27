# vlab-scan-runner: ตรวจ image.tar ของอาจารย์ด้วย Trivy + skopeo ก่อนเข้า camp registry
# รายละเอียดและเหตุผลด้านความปลอดภัย: docs/SCAN_RUNNER_IMAGE.md
#
# ทุก base image อ้างด้วย digest (ไม่ใช้ tag ลอย) ค่าจริงส่งมาจาก Ansible
# (ansible/roles/scan-runner-image/defaults/main.yml) ค่า default ข้างล่างต้องตรงกัน
# ไม่ใส่บรรทัด "# syntax=" เพราะจะดึง frontend image เพิ่มอีกตัวที่ไม่ได้ pin

# Trivy 0.76.1 (ตรวจ cosign กับ workflow release ของ aquasecurity แล้ว) ใช้แค่ binary
ARG TRIVY_IMAGE=ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c
ARG BASE_IMAGE=alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a

FROM ${TRIVY_IMAGE} AS trivy

FROM ${BASE_IMAGE}

ARG RUNNER_VERSION=1.0.0
ARG TRIVY_VERSION=0.76.1
LABEL org.opencontainers.image.title="vlab-scan-runner" \
      org.opencontainers.image.description="Scans uploaded lab image archives (Trivy + skopeo) before they reach the camp registry" \
      org.opencontainers.image.version="${RUNNER_VERSION}" \
      vlab.scan-runner.trivy-version="${TRIVY_VERSION}"

# - python3 รัน runner.py (stdlib อย่างเดียว), skopeo อ่าน/push image, ca-certificates ให้ TLS ไป R2 / Trivy DB
# - ถอด setuid/setgid ทุกไฟล์ และลบ apk ทิ้ง: ใน container ไม่มีทางติดตั้งอะไรเพิ่มหรือยกสิทธิ์ได้
# - user 10001 ไม่มี shell ไม่มี home (HOME ชี้ไป /work ที่เป็น volume)
RUN apk add --no-cache python3 skopeo ca-certificates \
 && addgroup -S -g 10001 scanner \
 && adduser -S -D -H -u 10001 -G scanner -s /sbin/nologin scanner \
 && mkdir -p /work /etc/vlab-scan /opt/vlab-scan \
 && chown 10001:10001 /work \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
 && rm -rf /sbin/apk /etc/apk /lib/apk /usr/share/apk /var/cache/apk/* /root/.cache

COPY --from=trivy /usr/local/bin/trivy /usr/local/bin/trivy
COPY policy.json /etc/vlab-scan/policy.json
COPY runner.py /opt/vlab-scan/runner.py

# ไฟล์ของ runner เป็นของ root และอ่านอย่างเดียว user 10001 แก้ไม่ได้
RUN chown root:root /usr/local/bin/trivy /etc/vlab-scan/policy.json /opt/vlab-scan/runner.py \
 && chmod 0555 /usr/local/bin/trivy /opt/vlab-scan/runner.py \
 && chmod 0444 /etc/vlab-scan/policy.json \
 && python3 -I -m py_compile /opt/vlab-scan/runner.py \
 && rm -rf /opt/vlab-scan/__pycache__

# root filesystem ใน Pod เป็น read-only ทุกอย่างที่เขียนต้องอยู่ใต้ /work
ENV HOME=/work \
    TMPDIR=/work/tmp \
    TRIVY_CACHE_DIR=/work/trivy-cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
WORKDIR /work

# -I: isolated mode ไม่อ่าน PYTHON* env และ user site-packages
ENTRYPOINT ["python3", "-I", "/opt/vlab-scan/runner.py"]
CMD ["version"]
