#!/bin/bash
# k3s-remove-local.sh - ลบ k3s ทุกอย่างออกจากเครื่องที่รัน (server และ/หรือ agent)
#
# ทำไมต้องมี: 1 เครื่องรัน k3s ได้ตัวเดียว ถ้าเครื่องเคยเป็น server มาก่อน (เช่น ThinkPad
# ที่เคยเทส playbook เป็น master) แล้วจะลงเป็น agent ของอีก cluster ตัว agent จะขึ้น
# "listen tcp 127.0.0.1:6444: bind: address already in use" แล้ว restart วนไม่จบ
#
# ห้ามใช้ k3s-agent-uninstall.sh ลบแค่ agent บนเครื่องที่มี server อยู่ด้วย เพราะมันเรียก
# k3s-killall.sh ก่อน ซึ่ง stop ทุก service ที่ชื่อ k3s* และ kill -9 pod ทุกตัวในเครื่อง
# แต่ไม่ลบข้อมูล (เห็นว่ามี service อื่นเหลือ) ได้ผลแย่ทั้งสองทาง
#
# ลำดับสำคัญ: ลบ unit ของ agent ก่อน ไม่งั้น k3s-uninstall.sh จะเห็นว่ามี service อื่นเหลือ
# แล้วข้ามการลบ binary / ข้อมูล
#
# สิ่งที่หาย: cluster ของเครื่องนี้ทั้งก้อน (pod, helm release, PVC ใน /var/lib/rancher/k3s),
# image cache ของ containerd และ /etc/rancher/k3s/registries.yaml (role k3s-agent เขียนให้ใหม่)
# ไม่แตะเครื่องอื่น: ไม่มีคำสั่งไหน ssh ออกไป
#
# ใช้:
#   ./script/k3s-remove-local.sh          # ถามชื่อเครื่องยืนยันก่อนลบ
#
# ลบเสร็จแล้วลงเป็น agent ใหม่ด้วย playbook (ดู ansible/inventory.home.yml)

set -e

HOST=$(hostname)

if ! ls /etc/systemd/system/k3s*.service >/dev/null 2>&1 && [ ! -e /usr/local/bin/k3s ]; then
  echo "==> เครื่อง $HOST ไม่มี k3s อยู่แล้ว ไม่มีอะไรให้ลบ"
  exit 0
fi

echo "==> service k3s บนเครื่อง $HOST"
systemctl list-units --all 'k3s*' --no-pager
echo
echo "จะลบ k3s และข้อมูล cluster ทั้งหมดบนเครื่องนี้ (pod / helm / PVC หายหมด)"
read -r -p "พิมพ์ชื่อเครื่อง ($HOST) เพื่อยืนยัน: " CONFIRM
if [ "$CONFIRM" != "$HOST" ]; then
  echo "==> ชื่อไม่ตรง ยกเลิก"
  exit 1
fi

echo "==> RAM ก่อนลบ"; free -h | head -2

echo "==> 1. ลบ agent (ถ้ามี)"
sudo systemctl disable --now k3s-agent 2>/dev/null || true
sudo systemctl reset-failed k3s-agent 2>/dev/null || true
sudo rm -f /etc/systemd/system/k3s-agent.service \
           /etc/systemd/system/k3s-agent.service.env \
           /usr/local/bin/k3s-agent-uninstall.sh
sudo systemctl daemon-reload

echo "==> 2. ลบ server + ข้อมูล (ถ้ามี)"
if [ -x /usr/local/bin/k3s-uninstall.sh ]; then
  sudo /usr/local/bin/k3s-uninstall.sh
else
  # มีแค่ agent: k3s-uninstall.sh ไม่มี ต้องเก็บกวาดเอง (killall ปลอดภัยเพราะไม่มี server แล้ว)
  [ -x /usr/local/bin/k3s-killall.sh ] && sudo /usr/local/bin/k3s-killall.sh
  sudo rm -rf /etc/rancher/k3s /run/k3s /run/flannel /var/lib/rancher/k3s /var/lib/kubelet \
              /usr/local/bin/k3s /usr/local/bin/k3s-killall.sh
fi

echo "==> 3. เช็กว่าสะอาด"
systemctl list-units --all 'k3s*' --no-pager
ss -ltn | grep -E ':(6443|6444|10250)\b' && echo "!! ยังมีพอร์ต k3s เปิดอยู่" || echo "พอร์ต 6443/6444/10250 ว่างแล้ว"
ls -d /usr/local/bin/k3s* /var/lib/rancher/k3s 2>/dev/null && echo "!! ยังมีไฟล์ k3s เหลือ" || echo "ไม่มีไฟล์ k3s เหลือ"

echo "==> RAM หลังลบ"; free -h | head -2
echo "==> เรียบร้อย"
