#!/bin/bash
# prepull.sh - ดึง image ลงเครื่องทุก node ล่วงหน้า ก่อนถึงคาบเรียน
#
# ทำไมต้องมี: วัดจริงบน cluster นี้แล้ว pod ที่ node ยังไม่มี image ใช้เวลา
# ~2 นาที 52 วินาที กว่าจะพร้อม แต่ถ้า image อยู่ใน cache ของ node แล้วเหลือ
# 4 วินาที (เร็วขึ้น 43 เท่า) - ถ้านักศึกษา 30 คนกดพร้อมกันตอนต้นคาบโดยไม่
# pre-pull ไว้ ทุกคนจะนั่งรอ registry ส่งไฟล์พร้อมกันหมด
#
# หลักการ: สร้าง DaemonSet ซึ่ง k8s จะวาง pod ลงทุก node ให้เอง พอ pod ดึง
# image เสร็จ containerd ของ node นั้นจะเก็บ layer ไว้ - ลบ DaemonSet ทิ้งได้
# เลย cache ไม่หายไปด้วย
#
# ใช้:
#   ./script/prepull.sh 100.127.74.48:5001/skypilot/music-lab:lab-01
#   ./script/prepull.sh img1 img2 img3        # หลายตัวพร้อมกันได้
#   ./script/prepull.sh --keep <image>        # ไม่ลบ DaemonSet ทิ้งหลังเสร็จ
#
# ต้องมี kubectl ที่ชี้ cluster ถูกอยู่แล้ว (KUBECONFIG หรือ ~/.kube/config)

set -e

NAMESPACE="${PREPULL_NAMESPACE:-default}"
DS_NAME="prepull"
KEEP=false

if [ "$1" = "--keep" ]; then
  KEEP=true
  shift
fi

if [ $# -eq 0 ]; then
  echo "ใช้: $0 [--keep] <image> [image...]"
  echo "ตัวอย่าง: $0 100.127.74.48:5001/skypilot/music-lab:lab-01"
  exit 1
fi

IMAGES=("$@")

echo "==> จะ pre-pull ${#IMAGES[@]} image ลงทุก node"
for img in "${IMAGES[@]}"; do echo "    - $img"; done

NODE_COUNT=$(kubectl get nodes --no-headers | wc -l | tr -d ' ')
echo "==> cluster มี $NODE_COUNT node"

# --- ประกอบ manifest ---
# แต่ละ image เป็น initContainer ที่ทำงานเสร็จแล้วจบทันที (exit 0) - k8s ต้อง
# ดึง image มาก่อนถึงจะรันได้ ซึ่งก็คือสิ่งที่เราต้องการ ส่วน container หลัก
# ใช้ image ตัวแรก (ดึงมาแล้ว) นอนรอเฉย ๆ ให้ DaemonSet คงสถานะ ready ไว้
# จะได้เช็คด้วย rollout status ได้ว่าครบทุก node หรือยัง
INIT_BLOCK=""
i=0
for img in "${IMAGES[@]}"; do
  INIT_BLOCK="${INIT_BLOCK}
        - name: pull-$i
          image: $img
          imagePullPolicy: IfNotPresent
          command: [\"/bin/sh\", \"-c\", \"exit 0\"]"
  i=$((i + 1))
done

MANIFEST=$(cat <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: $DS_NAME
  namespace: $NAMESPACE
spec:
  selector:
    matchLabels:
      app: $DS_NAME
  template:
    metadata:
      labels:
        app: $DS_NAME
    spec:
      # ลงให้ครบทุก node รวม control-plane ที่ปกติมี taint กันไว้
      tolerations:
        - operator: Exists
      terminationGracePeriodSeconds: 0
      initContainers:$INIT_BLOCK
      containers:
        - name: holder
          image: ${IMAGES[0]}
          imagePullPolicy: IfNotPresent
          command: ["/bin/sh", "-c", "sleep infinity"]
EOF
)

echo "==> สร้าง DaemonSet '$DS_NAME' ใน namespace '$NAMESPACE'"
echo "$MANIFEST" | kubectl apply -f -

START=$(date +%s)
echo "==> รอให้ทุก node ดึงเสร็จ (ครั้งแรกอาจนานหลายนาที ขึ้นกับขนาด image)"

if kubectl -n "$NAMESPACE" rollout status daemonset/"$DS_NAME" --timeout=30m; then
  ELAPSED=$(($(date +%s) - START))
  echo "==> เสร็จใน $ELAPSED วินาที ($NODE_COUNT node)"
else
  echo "==> rollout ไม่สำเร็จ - ดูสาเหตุจาก event ข้างล่าง"
  kubectl -n "$NAMESPACE" describe daemonset "$DS_NAME" | sed -n '/Events:/,$p' | head -20
  kubectl -n "$NAMESPACE" get pods -l app="$DS_NAME" -o wide
  exit 1
fi

echo "==> สถานะรายเครื่อง"
kubectl -n "$NAMESPACE" get pods -l app="$DS_NAME" \
  -o custom-columns='NODE:.spec.nodeName,STATUS:.status.phase' --no-headers

if [ "$KEEP" = true ]; then
  echo "==> --keep: ปล่อย DaemonSet ไว้ (ลบเองด้วย: kubectl -n $NAMESPACE delete ds $DS_NAME)"
else
  echo "==> ลบ DaemonSet ทิ้ง (image ที่ cache ไว้ยังอยู่ที่ node)"
  kubectl -n "$NAMESPACE" delete daemonset "$DS_NAME" --wait=true
fi

echo "==> เรียบร้อย"
