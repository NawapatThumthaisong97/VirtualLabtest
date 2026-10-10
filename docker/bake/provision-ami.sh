#!/usr/bin/env bash
# Bake AMI สำหรับ SkyPilot VM mode บน AWS (ใช้คู่กับ docker/bake/dockerfile ที่ใช้บน k8s)
#
# รันบน EC2 Ubuntu 22.04 (Canonical) เปล่า ๆ ในนาม user ubuntu:
#   bash provision-ami.sh ~/skypilot-0.12.3.post1-py3-none-any.whl
#
# ต่างจาก dockerfile:
# - SSH user ที่ SkyPilot ใช้บน AWS คือ ubuntu (ยืนยันจาก sky launch จริง) ทุก path เลยอยู่ใต้
#   /home/ubuntu ไม่ใช่ /home/sky
# - ไม่ useradd sky / ssh-keygen -A / CMD sshd: AMI มี sshd อยู่แล้ว และ host key ต้องให้
#   cloud-init สร้างใหม่ทุกเครื่อง ไม่งั้นทุก EC2 จาก AMI นี้จะได้ host key ชุดเดียวกัน
# - เพิ่ม Docker (รัน lab image) + AWS CLI v2 (login ECR) ถ้าไม่มี aws SkyPilot จะไปโหลดเองตอน
#   launch (docker_utils.py INSTALL_AWS_CLI_CMD)
# - สร้าง venv ด้วย Python ของ conda ตรง ๆ ไม่ให้ uv ไปโหลด Python เอง
#   (installer ของ uv โหลดจาก releases.astral.sh ก่อน ซึ่งมี IPv6 เลยใช้ใน private subnet ได้)
set -euo pipefail

WHEEL_SRC=${1:?usage: provision-ami.sh /path/to/skypilot-0.12.3.post1-py3-none-any.whl}

# ต้องตรงกับ SkyPilot API server ทุกตัว ไม่งั้นตอน provision จริงจะลงทับใหม่ (ดู dockerfile)
SKY_VERSION=0.12.3.post1
SKY_WHEEL_HASH=aa76e5f477bce4878b9e7543772faccd
RAY_VERSION=2.9.3

SKY_CONDA_ROOT="$HOME/miniconda3"
SKY_REMOTE_PYTHON_ENV="$HOME/skypilot-runtime"
UV="$HOME/.local/bin/uv"

echo "== apt: docker, patch, unzip =="
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  curl ca-certificates patch unzip rsync docker.io
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker

echo "== AWS CLI v2 + dual-stack =="
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip
unzip -q /tmp/awscli.zip -d /tmp
sudo /tmp/aws/install --update
rm -rf /tmp/aws /tmp/awscli.zip
mkdir -p "$HOME/.aws"
printf '[default]\nregion = ap-southeast-1\nuse_dualstack_endpoint = true\n' > "$HOME/.aws/config"

echo "== Miniconda (Python 3.10) =="
curl -fsSL "https://repo.anaconda.com/miniconda/Miniconda3-py310_23.11.0-2-Linux-x86_64.sh" \
  -o /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p "$SKY_CONDA_ROOT"
rm /tmp/miniconda.sh

echo "== uv (ปลายทาง ~/.local/bin = SKY_UV_INSTALL_DIR) =="
curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$HOME/.local/bin" sh

echo "== skypilot-runtime venv + ray =="
"$UV" venv --seed "$SKY_REMOTE_PYTHON_ENV" --python "$SKY_CONDA_ROOT/bin/python"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install "setuptools<70"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install "click<8.3.0"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install -U \
  "ray[default]==${RAY_VERSION}" "pydantic-core==2.41.1" "click<8.3.0"

echo "== SkyPilot wheel =="
WHEEL_DIR="$HOME/.sky/wheels/$SKY_WHEEL_HASH"
mkdir -p "$WHEEL_DIR"
cp "$WHEEL_SRC" "$WHEEL_DIR/skypilot-${SKY_VERSION}-py3-none-any.whl"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install \
  "$WHEEL_DIR/skypilot-${SKY_VERSION}-py3-none-any.whl[aws,remote]"
echo "$SKY_WHEEL_HASH" > "$HOME/.sky/wheels/current_sky_wheel_hash"

echo "== check =="
aws --version
docker --version
command -v patch
"$SKY_REMOTE_PYTHON_ENV/bin/python" -c \
  "import sky, ray; print('sky', sky.__version__, 'ray', ray.__version__)"
echo "provision done"
