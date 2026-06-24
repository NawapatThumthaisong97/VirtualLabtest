#!/bin/bash
################################################################################
# setup.sh — ติดตั้ง Prerequisites และ Load Credentials สำหรับ AI Learner Lab
#
# วิธีใช้:
#   1. cp credentials.env.example credentials.env
#   2. แก้ค่าใน credentials.env ให้ครบ
#   3. bash setup.sh
################################################################################

set -euo pipefail

echo "🔍 กำลังตรวจสอบและติดตั้ง Prerequisites..."
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# โหลด Credentials จาก credentials.env
# ══════════════════════════════════════════════════════════════════════════════

CRED_FILE="$(dirname "$0")/credentials.env"

if [ ! -f "$CRED_FILE" ]; then
    echo "❌ ไม่พบไฟล์ credentials.env"
    echo ""
    echo "   วิธีแก้:"
    echo "   cp credentials.env.example credentials.env"
    echo "   แล้วแก้ค่าให้ครบก่อน run สคริปต์นี้"
    exit 1
fi

# shellcheck disable=SC1090
source "$CRED_FILE"
echo "✅ โหลด credentials.env สำเร็จ"
echo ""

# ── ตรวจสอบว่ากรอก credential ครบหรือยัง ─────────────────────────────────────
MISSING=()
[ "${AWS_ACCESS_KEY_ID:-}" = "AKIA_REPLACE_ME" ]    && MISSING+=("AWS_ACCESS_KEY_ID")
[ "${AWS_SECRET_ACCESS_KEY:-}" = "REPLACE_ME_SECRET" ] && MISSING+=("AWS_SECRET_ACCESS_KEY")
[ "${TAILSCALE_AUTH_KEY:-}" = "tskey-auth-REPLACE_ME" ] && MISSING+=("TAILSCALE_AUTH_KEY")
[ "${CLOUDFLARE_TUNNEL_TOKEN:-}" = "REPLACE_ME_CLOUDFLARE_TOKEN" ] && MISSING+=("CLOUDFLARE_TUNNEL_TOKEN")
[ "${POSTGRES_PASSWORD:-}" = "REPLACE_ME_STRONG_PASSWORD" ] && MISSING+=("POSTGRES_PASSWORD")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "⚠️  credentials.env ยังกรอกไม่ครบ! ต้องแก้ค่าเหล่านี้ก่อน:"
    for key in "${MISSING[@]}"; do
        echo "   ❌ $key"
    done
    echo ""
    echo "   เปิดแก้ได้เลย: nano credentials.env"
    echo ""
    read -rp "กด Enter เพื่อดำเนินต่อ (เฉพาะ tools ที่ไม่ต้องใช้ credential) หรือ Ctrl+C เพื่อออก: "
fi

# ══════════════════════════════════════════════════════════════════════════════
# ตั้งค่า AWS CLI จาก credentials.env
# ══════════════════════════════════════════════════════════════════════════════

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION

echo "🔧 ตั้งค่า AWS CLI..."
if aws sts get-caller-identity &>/dev/null; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    echo "✅ AWS CLI พร้อมใช้งาน (Account: $ACCOUNT_ID)"
else
    echo "⚠️  AWS CLI ตรวจสอบ credentials ไม่สำเร็จ — ตรวจสอบ AWS_ACCESS_KEY_ID และ AWS_SECRET_ACCESS_KEY"
fi
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# 1. ตรวจสอบ Python 3 และ Pip
# ══════════════════════════════════════════════════════════════════════════════

echo "--- [1/5] Python 3 ---"
if ! command -v python3 &> /dev/null; then
    echo "⚠️ ไม่พบ Python3 กำลังติดตั้ง..."
    sudo apt update && sudo apt install -y python3 python3-pip python3-venv
else
    echo "✅ Python3 $(python3 --version) ติดตั้งแล้ว"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 2. ตรวจสอบ AWS CLI
# ══════════════════════════════════════════════════════════════════════════════

echo "--- [2/5] AWS CLI ---"
if ! command -v aws &> /dev/null; then
    echo "⚠️ ไม่พบ AWS CLI กำลังติดตั้ง..."
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    sudo apt install unzip -y
    unzip awscliv2.zip
    sudo ./aws/install
    rm -rf aws awscliv2.zip
else
    echo "✅ AWS CLI $(aws --version 2>&1 | cut -d' ' -f1) ติดตั้งแล้ว"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 3. ตรวจสอบ Tailscale
# ══════════════════════════════════════════════════════════════════════════════

echo "--- [3/5] Tailscale ---"
if ! command -v tailscale &> /dev/null; then
    echo "⚠️ ไม่พบ Tailscale กำลังติดตั้ง..."
    curl -fsSL https://tailscale.com/install.sh | sh
else
    echo "✅ Tailscale ติดตั้งแล้ว"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 4. ตรวจสอบ Docker
# ══════════════════════════════════════════════════════════════════════════════

echo "--- [4/5] Docker ---"
if ! command -v docker &> /dev/null; then
    echo "⚠️ ไม่พบ Docker กำลังติดตั้ง..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    rm get-docker.sh
else
    echo "✅ Docker $(docker --version | cut -d' ' -f3 | tr -d ',') ติดตั้งแล้ว"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5. ติดตั้ง Python Dependencies
# ══════════════════════════════════════════════════════════════════════════════

echo "--- [5/5] Python Dependencies ---"
if [ -f "requirements.txt" ]; then
    echo "📦 กำลังติดตั้ง Library จาก requirements.txt..."
    pip3 install -r requirements.txt
else
    echo "❌ ไม่พบไฟล์ requirements.txt ข้ามการติดตั้ง Library"
fi

# ══════════════════════════════════════════════════════════════════════════════
# สรุป
# ══════════════════════════════════════════════════════════════════════════════

echo ""
echo "════════════════════════════════════════════════"
echo "🎉 ติดตั้ง Prerequisites พื้นฐานเสร็จสมบูรณ์!"
echo ""
echo "📋 ขั้นตอนต่อไป:"
echo "   terraform init    → ใน infrastructure/terraform/"
echo "   terraform plan    → ตรวจสอบแผน (ใช้ TF_VAR_* จาก credentials.env)"
echo "   terraform apply   → Deploy จริง"
echo ""
echo "💡 Tip: ถ้าเปิด terminal ใหม่ ให้ run: source credentials.env"
echo "        เพื่อโหลด credentials กลับเข้ามา"
echo "════════════════════════════════════════════════"
