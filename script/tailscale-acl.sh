#!/bin/bash
# tailscale-acl.sh - ตั้ง Tailscale policy + tag เครื่องของ cluster ผ่าน API แทนการกดใน admin console
#
# ทำไมต้องมี: policy มีผลทั้ง tailnet ถ้าวางผิดใน console เครื่องแลปหลุดจาก cluster ทั้งหมด script นี้
# backup ของเดิมก่อนเสมอ ให้ Tailscale validate + รัน tests ก่อน แสดง diff แล้วถามยืนยันก่อนเขียนจริง
#
# token: ถามทุกครั้ง (พิมพ์แล้วไม่ขึ้นจอ) ไม่เก็บลงไฟล์ / history ถ้าตั้ง TS_API_KEY ไว้จะใช้ค่านั้นแทน
#   สร้างที่ admin console → Settings → Keys → API access tokens → Generate access token
#   ตั้งอายุ 1 วัน ให้หมดอายุ (revoke) เอง ไม่ต้องจำไปลบ
#
# ใช้ (รันจาก root ของ repo):
#   ./script/tailscale-acl.sh plan                  # ดูอย่างเดียว: backup + validate + diff + tag ที่จะติด
#   ./script/tailscale-acl.sh apply                 # plan แล้วถามยืนยัน → ตั้ง policy → ติด tag
#   ./script/tailscale-acl.sh rollback <backup>     # คืน policy จากไฟล์ backup (tailscale/backup/...)
#   ./script/tailscale-acl.sh check [node ...]      # ทดสอบจาก server / worker ทุกเครื่องใน vlab-tags.tsv (ไม่ใช้ token)
#                                                   # ใส่ชื่อ node เพื่อทดสอบเฉพาะเครื่องนั้น
#
# ไฟล์ (gitignore ทั้งหมด — แต่ละ cluster / tailnet มีของตัวเอง):
#   tailscale/vlab-acl.hujson (policy), tailscale/vlab-tags.tsv (IP → tag), tailscale/backup/
#   ครั้งแรก: cp tailscale/vlab-acl.hujson.example tailscale/vlab-acl.hujson (และ vlab-tags.tsv) แล้วแก้ IP / tag ของ cluster ตัวเอง

set -euo pipefail
trap 'printf "\033[?25h"' EXIT

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
POLICY="$ROOT/tailscale/vlab-acl.hujson"
TAGS="$ROOT/tailscale/vlab-tags.tsv"
BACKUP_DIR="$ROOT/tailscale/backup"
# ไม่ใช้ $KUBECONFIG ของ shell เพราะมักชี้ cluster อื่น (เครื่องนี้ชี้ minikube) ตั้ง VLAB_KUBECONFIG ถ้าจะเปลี่ยน
KUBECONFIG_FILE="${VLAB_KUBECONFIG:-$ROOT/web-portal/backend/kubeconfig.yaml}"
API="https://api.tailscale.com/api/v2"

die() { echo "!! $*" >&2; exit 1; }

# policy มีผลทั้ง tailnet ห้ามใช้ไฟล์ตัวอย่างของ cluster อื่นไปเขียนทับ tailnet ของเรา → ต้องมีไฟล์ของตัวเองก่อน
need_local_files() {
  local f
  for f in "$POLICY" "$TAGS"; do
    [ -f "$f" ] || die "ไม่มี ${f#$ROOT/} — cp ${f#$ROOT/}.example ${f#$ROOT/} แล้วแก้ให้ตรงกับ cluster / tailnet ของตัวเอง"
  done
}

banner() {
  local title="Virtual Lab : Tailscale ACL configuration" width
  width=$(tput cols 2>/dev/null || echo 80); [ "$width" -gt 100 ] && width=100
  local line; line=$(printf '%*s' $((width - ${#title} - 1)) '' | tr ' ' '-')
  # ตัวหนาเฉพาะตอนแสดงบน terminal (pipe ลงไฟล์ไม่มีรหัสสีปน)
  if [ -t 1 ]; then printf '\033[1m%s\033[0m %s\n' "$title" "$line"; else printf '%s %s\n' "$title" "$line"; fi
  printf '  mode: %s   policy: %s\n\n' "$1" "${POLICY#$ROOT/}"
}

need() { for c in "$@"; do command -v "$c" >/dev/null || die "ต้องมีคำสั่ง $c"; done; }

# ลูกเล่น: อักขระสีเขียววิ่งหลังใส่ token (แค่ตกแต่ง ไม่ได้ตรวจ token จริง ตรวจตอนเรียก API แรก)
# ไม่แสดงถ้าไม่ใช่ terminal หรือตั้ง VLAB_NO_FX=1
decrypt_fx() {
  [ -t 1 ] && [ -z "${VLAB_NO_FX:-}" ] || return 0
  local width i chars='a-zA-Z0-9;:!@#$%^&*()_+=-[]{}<>?/|~'
  width=$(tput cols 2>/dev/null || echo 80); [ "$width" -gt 100 ] && width=100
  printf '\033[?25l'                          # ซ่อน cursor ระหว่างวิ่ง
  for i in $(seq 1 28); do
    printf '\r\033[32m%s\033[0m' "$(LC_ALL=C tr -dc "$chars" </dev/urandom | head -c $((width - 1)))"
    sleep 0.035
  done
  printf '\r\033[K\033[1;32m>> token loaded — connecting to Tailscale API\033[0m\n\033[?25h'
}

ask_token() {
  if [ -n "${TS_API_KEY:-}" ]; then TOKEN="$TS_API_KEY"; return; fi
  read -rsp "Tailscale API access token: " TOKEN; echo
  [ -n "$TOKEN" ] || die "ไม่ได้ใส่ token"
  decrypt_fx
}

# token ส่งผ่าน config ของ curl ทาง stdin ไม่อยู่ใน argument (ps มองเห็น argument ได้)
api() {
  local method="$1" path="$2"; shift 2
  printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" | curl -sS -K - -X "$method" "$API$path" "$@"
}

backup_policy() {
  mkdir -p "$BACKUP_DIR"
  BACKUP="$BACKUP_DIR/acl-$(date +%Y%m%d-%H%M%S).hujson"
  local headers; headers=$(mktemp)
  api GET /tailnet/-/acl -H "Accept: application/hujson" -D "$headers" -o "$BACKUP"
  grep -q "^HTTP/[0-9.]* 200" "$headers" || { cat "$BACKUP" >&2; rm -f "$headers"; die "อ่าน policy ปัจจุบันไม่ได้ (token ถูกไหม / มีสิทธิ์ policy_file ไหม)"; }
  # ETag ใช้ตอนเขียน ถ้ามีคนแก้ใน console ระหว่างนี้ Tailscale จะตอบ 412 แทนการเขียนทับ
  ETAG=$(grep -i '^etag:' "$headers" | cut -d' ' -f2- | tr -d '\r')
  rm -f "$headers"
  echo "==> backup policy ปัจจุบัน: ${BACKUP#$ROOT/}"
}

validate_policy() {
  local file="$1" out
  # validate ตรวจ syntax และรัน "tests" ในไฟล์ (ตัวเดียวกับที่ console รันตอนกด Save)
  out=$(api POST /tailnet/-/acl/validate -H "Content-Type: application/hujson" --data-binary @"$file")
  if [ -n "$out" ] && [ "$out" != "{}" ] && echo "$out" | jq -e '.message // (.data | length > 0)' >/dev/null 2>&1; then
    echo "$out" | jq . >&2
    die "policy ไม่ผ่าน validate / tests ไม่ได้เขียนอะไร"
  fi
  echo "==> validate + tests ผ่าน: ${file#$ROOT/}"
}

show_diff() {
  echo "==> สิ่งที่จะเปลี่ยนใน policy (- ของเดิม / + ของใหม่)"
  diff -u --label "ปัจจุบัน" --label "ใหม่" "$BACKUP" "$POLICY" || true
}

# อ่าน tailscale/vlab-tags.tsv → "IP tag" ทีละบรรทัด (ตัดคอมเมนต์ / บรรทัดว่าง)
tag_rows() { sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$TAGS" | awk '{print $1, $2}'; }

plan_tags() {
  DEVICES=$(api GET "/tailnet/-/devices?fields=default")
  echo "==> tag ที่จะติด"
  TAG_PLAN=()
  while read -r ip tag; do
    local row id name current
    row=$(echo "$DEVICES" | jq -r --arg ip "$ip" '.devices[] | select(.addresses | index($ip)) | [.nodeId, .hostname, ((.tags // []) | join(","))] | @tsv')
    [ -n "$row" ] || { echo "   !! ไม่เจอเครื่อง $ip ใน tailnet (ข้าม)"; continue; }
    IFS=$'\t' read -r id name current <<<"$row"
    if [ "$current" = "$tag" ]; then
      printf "   %-16s %-14s %s (มีแล้ว)\n" "$ip" "$name" "$tag"
    else
      printf "   %-16s %-14s %s → %s\n" "$ip" "$name" "${current:-ไม่มี tag}" "$tag"
      TAG_PLAN+=("$id $tag $name")
    fi
  done < <(tag_rows)
}

confirm() {
  read -rp "$1 พิมพ์ yes เพื่อยืนยัน: " ans
  [ "$ans" = "yes" ] || die "ยกเลิก ไม่ได้เขียนอะไร"
}

write_policy() {
  local file="$1" code body
  body=$(mktemp)
  code=$(api POST /tailnet/-/acl -H "Content-Type: application/hujson" -H "If-Match: $ETAG" \
    --data-binary @"$file" -o "$body" -w "%{http_code}")
  if [ "$code" = "412" ]; then rm -f "$body"; die "policy ถูกแก้ระหว่างนี้ (ETag ไม่ตรง) รันใหม่อีกรอบ"; fi
  [ "$code" = "200" ] || { cat "$body" >&2; rm -f "$body"; die "ตั้ง policy ไม่สำเร็จ (HTTP $code)"; }
  rm -f "$body"
  echo "==> ตั้ง policy แล้ว (คืนได้ด้วย: $0 rollback ${BACKUP#$ROOT/})"
}

apply_tags() {
  local item id tag name
  for item in "${TAG_PLAN[@]+"${TAG_PLAN[@]}"}"; do
    read -r id tag name <<<"$item"
    api POST "/device/$id/tags" -H "Content-Type: application/json" -d "{\"tags\":[\"$tag\"]}" >/dev/null
    echo "   ติด $tag ให้ $name"
  done
  echo "==> ติด tag ครบแล้ว ทดสอบต่อด้วย: $0 check"
}

# ---------- check: ทดสอบจากเครื่องจริง (ไม่ใช้ token) ----------
# debug pod แบบ hostNetwork ใช้ตัวตน Tailscale ของ node นั้น = เหมือนนั่งที่เครื่อง
# image = scanner ใน camp registry (มี python3 อยู่แล้ว) ไม่ต้องดึงจาก Docker Hub และ imagePullPolicy Always
# พิสูจน์ไปด้วยว่า node นั้น pull จาก :5001 ผ่าน ACL ได้จริง เปลี่ยน image ได้ด้วย VLAB_PROBE_IMAGE

CHECK_POD=vlab-acl-check
# ต่อ TCP ด้วย python (image ไม่มี nc) argv: host port
PY_CONNECT='import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 3).close()'
# ถาม coredns ของ cluster (dnsPolicy ClusterFirstWithHostNet) = วิ่งผ่าน VXLAN ไป master
PY_DNS='import socket; socket.getaddrinfo("kubernetes.default.svc.cluster.local", 443)'

# IP ของเครื่องที่ติด tag นี้ใน vlab-tags.tsv (บรรทัดละเครื่อง)
tag_ips() { tag_rows | awk -v t="$1" '$2 == t {print $1}'; }

check_result() {  # check_result <ok?> <ข้อความ>
  if [ "$1" = yes ]; then CHECK_PASS=$((CHECK_PASS + 1)); echo "   ok   $2"
  else CHECK_FAIL=$((CHECK_FAIL + 1)); echo "   FAIL $2"; fi
}

probe() {  # probe <ชื่อ> <host> <port> <open|closed>
  local got
  if $K exec "$CHECK_POD" -- python3 -I -c "$PY_CONNECT" "$2" "$3" >/dev/null 2>&1; then got=open; else got=closed; fi
  check_result "$([ "$got" = "$4" ] && echo yes)" "$(printf '%-24s %s:%-5s ต้อง %-6s ได้ %s' "$1" "$2" "$3" "$4" "$got")"
}

check_node() {  # check_node <node> <tag>
  local node="$1" role="$2" ip
  $K delete pod "$CHECK_POD" --ignore-not-found --wait=true >/dev/null
  $K run "$CHECK_POD" --image="$PROBE_IMAGE" --restart=Never --image-pull-policy=Always \
    --overrides="{\"spec\":{\"hostNetwork\":true,\"dnsPolicy\":\"ClusterFirstWithHostNet\",\"terminationGracePeriodSeconds\":0,\"nodeSelector\":{\"kubernetes.io/hostname\":\"$node\"}}}" \
    --command -- python3 -I -c 'import time; time.sleep(600)' >/dev/null
  echo "==> จาก $node ($role)"
  if ! $K wait --for=condition=Ready "pod/$CHECK_POD" --timeout=180s >/dev/null 2>&1; then
    check_result no "pull $PROBE_IMAGE ไม่ขึ้นใน 180 วินาที (ACL ปิด :5001?)"
    $K describe pod "$CHECK_POD" | sed -n '/^Events:/,$p' | tail -n 5 | sed 's/^/        /'
    $K delete pod "$CHECK_POD" --wait=false >/dev/null
    return
  fi
  check_result yes "pull $PROBE_IMAGE"

  case "$role" in
    tag:vlab-worker)
      for ip in $SERVER_IPS; do
        probe "server k3s api" "$ip" 6443 open
        probe "server kubelet" "$ip" 10250 closed
        probe "server ssh" "$ip" 22 closed
      done
      probe "registry pull" "$REGISTRY_IP" 5001 open
      probe "registry push" "$REGISTRY_IP" 5002 closed
      probe "registry ssh" "$REGISTRY_IP" 22 closed
      ;;
    tag:vlab-server)
      probe "registry pull" "$REGISTRY_IP" 5001 open
      probe "registry push" "$REGISTRY_IP" 5002 open
      for ip in $WORKER_IPS; do probe "worker kubelet" "$ip" 10250 open; done
      ;;
  esac
  if $K exec "$CHECK_POD" -- python3 -I -c "$PY_DNS" >/dev/null 2>&1; then
    check_result yes "DNS ของ cluster (coredns ผ่าน VXLAN)"
  else
    check_result no "DNS ของ cluster (coredns ผ่าน VXLAN)"
  fi
  $K delete pod "$CHECK_POD" --wait=false >/dev/null
}

check() {
  need kubectl
  K="kubectl --kubeconfig $KUBECONFIG_FILE"
  REGISTRY_IP=$(tag_ips tag:vlab-registry | head -n1)
  SERVER_IPS=$(tag_ips tag:vlab-server)
  WORKER_IPS=$(tag_ips tag:vlab-worker)
  [ -n "$REGISTRY_IP" ] || die "ไม่มีเครื่อง tag:vlab-registry ใน ${TAGS#$ROOT/}"
  PROBE_IMAGE="${VLAB_PROBE_IMAGE:-$REGISTRY_IP:5001/vlab/scan-runner:1.1.0}"
  CHECK_PASS=0; CHECK_FAIL=0

  # ชื่อ node หาจาก IP (k3s ตั้ง --node-ip เป็น Tailscale IP) ไม่ต้องจำชื่อเครื่อง
  local nodes targets=() ip role name
  nodes=$($K get nodes -o jsonpath='{range .items[*]}{.status.addresses[?(@.type=="InternalIP")].address}{" "}{.metadata.name}{"\n"}{end}')
  while read -r ip role; do
    case "$role" in tag:vlab-server|tag:vlab-worker) ;; *) continue ;; esac
    name=$(echo "$nodes" | awk -v ip="$ip" '$1 == ip {print $2}')
    [ -n "$name" ] || { echo "   !! ไม่เจอ node ที่ IP $ip ใน cluster (ข้าม)"; continue; }
    # ใส่ชื่อ node มา = ทดสอบเฉพาะเครื่องนั้น
    [ $# -eq 0 ] || printf '%s\n' "$@" | grep -qx "$name" || continue
    targets+=("$name $role")
  done < <(tag_rows)
  [ ${#targets[@]} -gt 0 ] || die "ไม่มี node ให้ทดสอบ"

  # วนจาก array ไม่ใช่ใน while read: kubectl exec อาจกิน stdin ของ loop
  local item
  for item in "${targets[@]}"; do check_node $item; done

  echo "==> node"; $K get nodes --no-headers | awk '{printf "   %-14s %s\n", $1, $2}'
  echo "==> ผ่าน $CHECK_PASS / ไม่ผ่าน $CHECK_FAIL"
  [ "$CHECK_FAIL" -eq 0 ]
}

cmd="${1:-}"; shift || true
case "$cmd" in plan|apply|check) need_local_files ;; esac
case "$cmd" in plan|apply|rollback|check) banner "$cmd" ;; esac
case "$cmd" in
  plan)
    need curl jq diff; ask_token
    backup_policy; validate_policy "$POLICY"; show_diff; plan_tags
    echo "==> plan อย่างเดียว ไม่ได้เขียนอะไร"
    ;;
  apply)
    need curl jq diff; ask_token
    backup_policy; validate_policy "$POLICY"; show_diff; plan_tags
    confirm "จะตั้ง policy ใหม่ (มีผลทั้ง tailnet) แล้วติด tag ${#TAG_PLAN[@]} เครื่อง"
    write_policy "$POLICY"; apply_tags
    ;;
  rollback)
    file="${1:-}"; [ -f "$file" ] || die "ใช้: $0 rollback tailscale/backup/acl-....hujson"
    need curl jq diff; ask_token
    backup_policy; validate_policy "$file"
    diff -u --label "ปัจจุบัน" --label "จะคืนเป็น" "$BACKUP" "$file" || true
    confirm "จะคืน policy เป็น ${file}"
    write_policy "$file"
    echo "==> tag ของเครื่องยังอยู่ (ไม่มีผลถ้า policy เดิมเปิดหมด) แก้ tag ได้ที่ console หรือ vlab-tags.tsv"
    ;;
  check) check "$@" ;;
  *) sed -n '2,18p' "$0"; exit 1 ;;
esac
