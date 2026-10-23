#!/bin/bash
# tailscale-acl.sh - ตั้ง Tailscale policy + tag เครื่องของ cluster ผ่าน API แทนการกดใน admin console
#
# ทำไมต้องมี: policy มีผลทั้ง tailnet ถ้าวางผิดใน console เครื่องแลปหลุดจาก cluster ทั้งหมด script นี้
# backup ของเดิมก่อนเสมอ ให้ Tailscale validate + รัน tests ก่อน แสดง diff แล้วถามยืนยันก่อนเขียนจริง
#
# token: ถามทุกครั้ง (พิมพ์แล้วไม่ขึ้นจอ) ไม่เก็บลงไฟล์ / history ถ้าตั้ง TS_API_KEY ไว้จะใช้ค่านั้นแทน
#   สร้างที่ admin console → Settings → Keys → Generate access token (ตั้งอายุสั้น ๆ พอ)
#
# ใช้ (รันจาก root ของ repo):
#   ./script/tailscale-acl.sh plan                  # ดูอย่างเดียว: backup + validate + diff + tag ที่จะติด
#   ./script/tailscale-acl.sh apply                 # plan แล้วถามยืนยัน → ตั้ง policy → ติด tag
#   ./script/tailscale-acl.sh rollback <backup>     # คืน policy จากไฟล์ backup (tailscale/backup/...)
#   ./script/tailscale-acl.sh check [worker]        # ทดสอบจาก worker ด้วย debug pod (ไม่ใช้ token)
#
# ไฟล์: tailscale/vlab-acl.hujson (policy), tailscale/vlab-tags.tsv (IP → tag), tailscale/backup/ (gitignore)

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

# ทดสอบจากเครื่อง worker ด้วย debug pod hostNetwork (ใช้ตัวตน Tailscale ของเครื่องนั้น = เหมือนนั่งที่เครื่อง)
check() {
  need kubectl
  local worker="${1:-worker-pete}" K="kubectl --kubeconfig $KUBECONFIG_FILE"
  $K delete pod vlab-acl-check --ignore-not-found --wait=true >/dev/null
  # imagePullPolicy Always = ทดสอบว่ายัง pull จาก registry ผ่าน ACL ได้จริง
  $K run vlab-acl-check --image=100.127.74.48:5001/vlab/hello:v1 --restart=Never --image-pull-policy=Always \
    --overrides="{\"spec\":{\"hostNetwork\":true,\"terminationGracePeriodSeconds\":0,\"nodeSelector\":{\"kubernetes.io/hostname\":\"$worker\"}}}" \
    --command -- sleep 600 >/dev/null
  $K wait --for=condition=Ready pod/vlab-acl-check --timeout=120s >/dev/null || die "debug pod ไม่ขึ้นบน $worker (pull image ไม่ผ่าน?)"
  echo "==> pull image จาก registry บน $worker ได้"

  local pass=0 fail=0
  probe() {  # probe <ชื่อ> <host> <port> <open|closed>
    local got
    if $K exec vlab-acl-check -- nc -z -w 3 "$2" "$3" 2>/dev/null; then got=open; else got=closed; fi
    if [ "$got" = "$4" ]; then pass=$((pass + 1)); s="ok  "; else fail=$((fail + 1)); s="FAIL"; fi
    printf "   %s %-24s %s:%-5s ต้อง %-6s ได้ %s\n" "$s" "$1" "$2" "$3" "$4" "$got"
  }
  echo "==> จาก $worker"
  probe "master k3s api" 100.125.244.48 6443 open
  probe "registry" 100.127.74.48 5001 open
  probe "thinkpad backend" 100.93.121.17 8000 open
  probe "thinkpad kubelet" 100.93.121.17 10250 closed
  probe "thinkpad ssh" 100.93.121.17 22 closed
  probe "master ssh" 100.125.244.48 22 closed
  probe "registry ssh" 100.127.74.48 22 closed
  if $K exec vlab-acl-check -- nslookup kubernetes.default.svc.cluster.local 10.43.0.10 >/dev/null 2>&1; then
    pass=$((pass + 1)); echo "   ok   DNS ของ cluster (coredns บน master ผ่าน VXLAN)"
  else
    fail=$((fail + 1)); echo "   FAIL DNS ของ cluster (coredns บน master ผ่าน VXLAN)"
  fi
  echo "==> node"; $K get nodes --no-headers | awk '{printf "   %-14s %s\n", $1, $2}'
  $K delete pod vlab-acl-check --wait=false >/dev/null
  echo "==> ผ่าน $pass / ไม่ผ่าน $fail"
  [ "$fail" -eq 0 ]
}

cmd="${1:-}"; shift || true
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
  *) sed -n '2,20p' "$0"; exit 1 ;;
esac
