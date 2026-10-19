#!/bin/bash
# launch-test.sh - เทสเปิด / ปิด lab ผ่าน API ของ backend ด้วย curl (แบบอยู่ใน docs/LAUNCH_CONSOLE.md)
#
# ยิงแค่ API ของ backend เหมือนหน้าเว็บ ไม่สร้าง pod / ไม่แก้ DB / ไม่เรียก kubectl, AWS, SkyPilot ตรง
# backend เห็น IP ของเครื่องที่รัน script นี้:
#   - รันบนเครื่อง worker (หรือ ThinkPad ด้วย Tailscale IP) = เหมือนนักศึกษากดจากเครื่องแลป → warm pod / pin เครื่อง
#   - BACKEND_URL=http://127.0.0.1:8000 = ไม่ผูกกับเครื่องไหน
#
# ใช้ (รันจาก root ของ repo ต้องมี curl + jq):
#   ./script/launch-test.sh
#   BACKEND_URL=http://100.93.121.17:8000 ./script/launch-test.sh      # ให้ backend เห็นเป็นเครื่อง thinkpad
#
# ค่าตั้งต้นแก้ด้วย env: BACKEND_URL USER_ID USER_NAME LAB_K8S LAB_AWS LAB_AUTO SKY_URL REGISTRY (ปิดลูกเล่น: VLAB_NO_FX=1)

set -u

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
API="$BACKEND_URL/api"
USER_ID="${USER_ID:-b4f5c004-5dac-4e38-99cb-8382d5982484}"     # Sophia Davis (persona seed)
USER_NAME="${USER_NAME:-Sophia Davis}"
LAB_K8S="${LAB_K8S:-03a18386-1558-4bcf-9399-4b79cc1ae22b}"     # OOP with Spring Boot (run_target KUBERNETES)
LAB_AWS="${LAB_AWS:-536989c2-52d1-4169-b23a-ed06247cdb57}"     # OOP with Spring Boot (AWS)
LAB_AUTO="${LAB_AUTO:-035a1861-3b1b-4309-8600-22cab0d06439}"   # OOP with Spring Boot (AUTO): เครื่องแลป → K8s, ที่อื่น → AWS
SKY_URL="${SKY_URL:-http://100.125.244.48:30880}"              # SkyPilot กลางบน master (NodePort ผ่าน Tailscale)
REGISTRY="${REGISTRY:-100.127.74.48:5001}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"; [ -t 1 ] && printf "\033[?25h"' EXIT

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  G=$'\033[32m'; B=$'\033[1;92m'; D=$'\033[2;32m'; R=$'\033[1;31m'; Y=$'\033[33m'; W=$'\033[1;97m'; N=$'\033[0m'
else
  G=; B=; D=; R=; Y=; W=; N=
fi

die() { echo "${R}!! $*${N}" >&2; exit 1; }
for c in curl jq; do command -v "$c" >/dev/null || die "missing command: $c"; done

get()  { curl -s --max-time "${2:-10}" "$1"; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time "${2:-5}" "$1"; }
line() { printf '%*s' "${1:-78}" '' | tr ' ' "${2:--}"; }
short() { echo "${1:0:8}"; }

# ---------- ลูกเล่นตอนเปิด: ตัวอักษรเขียวไหล 1 วิ (แค่ตกแต่ง)
matrix_fx() {
  [ -t 1 ] && [ -z "${VLAB_NO_FX:-}" ] || return 0
  local width=$(( $(tput cols 2>/dev/null || echo 80) > 100 ? 100 : $(tput cols 2>/dev/null || echo 80) )) i
  local chars='ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄ0123456789:=*+<>'
  printf '\033[?25l'
  for i in $(seq 1 14); do
    local row="" j
    for j in $(seq 1 $((width - 1))); do
      if (( RANDOM % 4 == 0 )); then row+="${chars:RANDOM%${#chars}:1}"; else row+=" "; fi
    done
    printf '%s%s%s\n' "$( (( i % 3 == 0 )) && echo "$B" || echo "$G")" "$row" "$N"
    sleep 0.04
  done
  printf '%s>> wake up, lab... connecting to %s%s\n\033[?25h' "$B" "$BACKEND_URL" "$N"
  sleep 0.3
}

# ---------- แถบสถานะ
word() { [ "$1" = ok ] && echo "${B}active${N}" || echo "${R}down${N}"; }

lab_title() { get "$API/labs/$1" 5 | jq -r '.data.title // "?"'; }

banner() {
  local backend sky registry nodes master workers k8s_title aws_title auto_title
  [ "$(code "$BACKEND_URL/health")" = 200 ] && backend=ok || backend=down
  [ "$(get "$SKY_URL/api/health" 4 | jq -r '.status // empty' 2>/dev/null)" = healthy ] && sky=ok || sky=down
  [ "$(code "http://$REGISTRY/v2/" 4)" = 200 ] && registry=ok || registry=down
  nodes=$(get "$API/kubernetes/nodes" 8)
  master=$(echo "$nodes" | jq -r '[.nodes[]? | select(.labels["node-role.kubernetes.io/control-plane"]) | select(.ready == "True")] | if length > 0 then "ok" else "down" end' 2>/dev/null)
  workers=$(echo "$nodes" | jq -r '[.nodes[]? | select(.labels["node-role.kubernetes.io/control-plane"] | not)] | "\(map(select(.ready == "True")) | length)/\(length)"' 2>/dev/null)
  k8s_title=$(lab_title "$LAB_K8S"); aws_title=$(lab_title "$LAB_AWS"); auto_title=$(lab_title "$LAB_AUTO")

  echo
  echo "${B}Virtual Lab : Launch Test${N} ${G}$(line 52)${N}"
  echo " Master : $(word "${master:-down}") | Registry : $(word $registry) | Sky : $(word $sky) | Worker : ${B}${workers:-?} ready${N} | Backend : $(word $backend)"
  echo " User : ${G}${USER_NAME}${N} | Backend : ${G}${BACKEND_URL}${N}"
  echo " Lab K8s : ${G}${k8s_title}${N} | Lab AWS : ${G}${aws_title}${N} | Lab AUTO : ${G}${auto_title}${N}"
  echo "${D}$(line 78)${N}"
  menu
}

menu() {
  echo " ${B}1)${N} Start K8s  ${B}2)${N} Start AWS  ${B}3)${N} Start AUTO  ${B}4)${N} Warm pods  ${B}5)${N} Sessions  ${B}6)${N} Terminate  ${B}7)${N} Scheduler  ${B}r)${N} Refresh  ${B}q)${N} Quit"
}

# ---------- 1 / 2 / 3 Start lab
start_lab() {
  local lab="$1" kind="$2" pid t0 el http frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏' i=0
  echo "${W}POST${N} /api/sessions  ${D}lab :${N} ${G}$(lab_title "$lab")${N} ${D}(${kind})${N}"
  t0=$SECONDS
  curl -s --max-time 1500 -o "$TMP/resp.json" -w '%{http_code}' -X POST "$API/sessions" \
    -H 'Content-Type: application/json' -d "{\"lab_id\":\"$lab\",\"user_id\":\"$USER_ID\"}" > "$TMP/code" &
  pid=$!
  # Ctrl+C = เลิกรอ (backend ยัง launch ต่อ ดูด้วยเมนู 4)
  trap 'kill $pid 2>/dev/null; echo; echo "${Y}stopped waiting — backend keeps launching, check with 5${N}"' INT
  [ -t 1 ] && printf '\033[?25l'
  while kill -0 "$pid" 2>/dev/null; do
    el=$((SECONDS - t0))
    [ -t 1 ] && printf '\r%s%s%s %swaiting for backend ...%s %02d:%02d ' "$B" "${frames:i++%10:1}" "$N" "$G" "$N" $((el / 60)) $((el % 60))
    sleep 0.15
  done
  wait "$pid" 2>/dev/null
  trap - INT
  [ -t 1 ] && printf '\r\033[K\033[?25h'
  el=$((SECONDS - t0)); http=$(cat "$TMP/code" 2>/dev/null)
  [ -s "$TMP/resp.json" ] || { echo "${R}✖ no response from backend (HTTP ${http:-0})${N}"; return; }

  if [ "$http" = 201 ] && jq -e '.success' "$TMP/resp.json" >/dev/null; then
    jq -r --arg el "$el" --arg B "$B" --arg G "$G" --arg D "$D" --arg N "$N" '
      .data as $d
      | "\($B)✅ success \($el)s\($N)   \($D)target :\($N) \($B)\($d.run_target // "?")\($N)   \($D)mode :\($N) \($G)\($d.launch_mode)\($N)"
        + (if $d.node_name then "   \($D)node :\($N) \($G)\($d.node_name)\($N)" else "" end)
        + (if $d.cluster_name then "   \($D)cluster :\($N) \($G)\($d.cluster_name)\($N)" else "" end),
        ($d.endpoints // {} | to_entries | sort_by(.key)[] | "   \($G)\(.key)\($N)  \(.value)"),
        "   \($D)session :\($N) \($d.session_id)   \($D)expires :\($N) \($d.expires_at)"' "$TMP/resp.json"
  else
    echo "${R}✖ failed (HTTP $http, ${el}s)${N} $(jq -r '.message // .detail // .' "$TMP/resp.json" | cut -c1-400)"
  fi
}

# ---------- 4 Warm pods
warm_pods() {
  echo "${W}GET${N} /api/warm-pods"
  local rows
  rows=$(get "$API/warm-pods" 10 | jq -r --arg B "$B" --arg Y "$Y" --arg D "$D" --arg N "$N" '
    .data // [] | .[] | "   \(.pod)\t\(.node)\t\(if .state == "free" then "\($B)free\($N)" else "\($Y)\(.state)\($N)" end)\t\(if .ready then "ready" else "\($D)\(.phase)\($N)" end)\t\(.session_id // "-" | .[0:8])"')
  if [ -z "$rows" ]; then
    echo "   ${D}no warm pods (created only for class slots that are starting / in progress)${N}"
  else
    { echo "   ${D}POD	NODE	STATE	READY	SESSION${N}"; echo "$rows"; } | column -t -s $'\t'
  fi
}

# ---------- 5 Sessions (เฉพาะของ user ที่ยังเปิดอยู่)
active_sessions() {
  get "$API/sessions" 10 | jq -c --arg u "$USER_ID" --arg k8s "$LAB_K8S" --arg aws "$LAB_AWS" --arg auto "$LAB_AUTO" '
    [.data // [] | .[] | select(.user_id == $u and (.status == "running" or .status == "pending"))
     | {id, status, lab: (if .lab_id == $aws then "AWS" elif .lab_id == $k8s then "K8s" elif .lab_id == $auto then "AUTO" else "other" end),
        where: (if .is_cloud then "EC2 \(.sky_cluster_name // "")"
                elif .sky_cluster_name then "skypilot \(.sky_cluster_name)"
                elif .k8s_pod_name then "warm pod \(.k8s_pod_name)"
                else "-" end),
        node: (.node_name // "-")}]'
}

show_sessions() {
  local list="$1" n
  n=$(echo "$list" | jq 'length')
  if [ "$n" = 0 ]; then echo "   ${D}${USER_NAME} has no open sessions${N}"; return 1; fi
  echo "$list" | jq -r --arg G "$G" --arg N "$N" \
    'to_entries[] | " \($G)\(.key + 1))\($N) \(.value.id[0:8])\t\(.value.status)\t\(.value.lab)\t\(.value.where)\t\(.value.node)"' \
    | column -t -s $'\t'
}

sessions() {
  echo "${W}GET${N} /api/sessions  ${D}(running / pending of ${USER_NAME})${N}"
  show_sessions "$(active_sessions)" || true
}

# ---------- 6 Terminate
delete_session() {
  local id="$1" t0=$SECONDS http
  printf '%sDELETE%s /api/sessions/%s… ' "$W" "$N" "$(short "$id")"
  http=$(curl -s --max-time 300 -o "$TMP/del.json" -w '%{http_code}' -X DELETE "$API/sessions/$id")
  if [ "$http" = 200 ]; then
    echo "${B}✅ $(jq -r '.data.message // .message' "$TMP/del.json")${N} ${D}($((SECONDS - t0))s)${N}"
  else
    echo "${R}✖ HTTP $http $(jq -r '.message // .' "$TMP/del.json" 2>/dev/null | cut -c1-300)${N}"
  fi
}

terminate() {
  local list n pick ids=()
  list=$(active_sessions)
  show_sessions "$list" || return
  n=$(echo "$list" | jq 'length')
  read -rp " pick session (number / all / Enter = cancel): " pick
  case "$pick" in
    "") echo " ${D}cancelled${N}"; return ;;
    all) mapfile -t ids < <(echo "$list" | jq -r '.[].id') ;;
    *) [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= n )) || { echo " ${Y}no session #$pick${N}"; return; }
       ids=("$(echo "$list" | jq -r ".[$((pick - 1))].id")") ;;
  esac
  read -rp " ${Y}delete ${#ids[@]} session(s)? [y/N]${N} " ans
  [ "$ans" = y ] || { echo " ${D}cancelled${N}"; return; }
  for id in "${ids[@]}"; do delete_session "$id"; done
}

# ---------- 7 Scheduler (GET /api/prewarm/schedule + /api/prewarm + /api/warm-pods)
# LC_ALL=C = ชื่อวัน / เดือนเป็นภาษาอังกฤษเสมอ (เครื่องที่ตั้ง locale ไทยจะได้ "ศ. 23 ต.ค.")
fmt_time() { LC_ALL=C date -d "$1" '+%a %d %b %H:%M' 2>/dev/null || echo "$1"; }
hhmm()     { LC_ALL=C date -d "$1" '+%H:%M' 2>/dev/null || echo "$1"; }

until_str() {
  local s=$(( $(date -d "$1" +%s) - $(date +%s) ))
  (( s <= 0 )) && { echo "now"; return; }
  local d=$((s / 86400)) h=$((s % 86400 / 3600)) m=$((s % 3600 / 60))
  if (( d > 0 )); then echo "in ${d}d ${h}h"; elif (( h > 0 )); then echo "in ${h}h ${m}m"; else echo "in ${m}m $((s % 60))s"; fi
}

scheduler_view() {
  local data what starts ends prewarm course image status active note
  data=$(get "$API/prewarm/schedule?limit=${1:-5}" 10)
  if ! echo "$data" | jq -e '.success' >/dev/null 2>&1; then
    echo "   ${R}✖ GET /api/prewarm/schedule failed (backend down or too old?)${N}"; return
  fi
  echo "${W}GET${N} /api/prewarm/schedule  ${D}($(date '+%H:%M:%S'))${N}"
  echo "$data" | jq -r --arg B "$B" --arg R "$R" --arg G "$G" --arg N "$N" '.data |
    " Scheduler : \(if .enabled then "\($B)on\($N)" else "\($R)off\($N)" end)  every \(.interval_seconds)s | starts \(.lead_minutes) min before class | warm pod : \(if .warm_pod_enabled then "\($B)on\($N)" else "off" end)"'
  what=$(echo "$data" | jq -r 'if .data.warm_pod_enabled then "pre-pull + warm pod" else "pre-pull" end')

  echo " ${G}Upcoming class slots${N}"
  if [ "$(echo "$data" | jq '.data.slots | length')" = 0 ]; then
    echo "   ${D}none — scheduler has nothing to do${N}"
  fi
  while IFS=$'\t' read -r starts ends prewarm course image status active note; do
    printf '   %s–%s  %s%s%s  %s  %s\n' "$(fmt_time "$starts")" "$(hhmm "$ends")" "$G" "$course" "$N" "${image#*/}" "$status"
    if [ "$active" = true ]; then
      echo "     ${B}● active now${N} — $what running, removed at $(hhmm "$ends") ($(until_str "$ends"))"
    else
      echo "     → $what starts $(fmt_time "$prewarm") ${B}($(until_str "$prewarm"))${N} | removed at $(hhmm "$ends")"
    fi
    [ -n "$note" ] && echo "     ${D}note: $note${N}"
  done < <(echo "$data" | jq -r '.data.slots[] | [.starts_at, .ends_at, .prewarm_at, (.course_code // "-"), .image, .status, (.active | tostring), (.note // "")] | @tsv')

  if [ "$(echo "$data" | jq '.data.targets | length')" != 0 ]; then
    echo " ${G}.env PREWARM_TARGETS${N} ${D}(pre-pull only)${N}"
    echo "$data" | jq -r --arg B "$B" --arg N "$N" '.data.targets[] |
      "   \(.image | sub("^[^/]+/"; ""))  \(.start_at) → \(.end_at)\(if .active then "  \($B)● active\($N)" else "" end)"'
  fi

  local ds warm
  ds=$(get "$API/prewarm" 10 | jq -r '.data // [] | map("\(.image | sub("^[^/]+/"; "")) \(.ready)/\(.desired) pulled") | if length == 0 then "none" else join(", ") end')
  warm=$(get "$API/warm-pods" 10 | jq -r '.data // [] | "\(length) (free \(map(select(.state == "free")) | length))"')
  echo " ${G}Right now${N}  pre-pull DaemonSet : ${ds:-?} | warm pods : ${warm:-?}"
}

scheduler() {
  scheduler_view 5
  read -rp " ${D}w = watch live (every 5s), Enter = back:${N} " ans
  [ "$ans" = w ] || return
  # live: วาดใหม่ทุก 5 วิ กดปุ่มอะไรก็ได้เพื่อออก
  while true; do
    [ -t 1 ] && printf '\033[H\033[2J'
    echo "${B}Scheduler — live${N} ${D}(press any key to stop)${N}"
    scheduler_view 5
    read -rsn 1 -t 5 && break
  done
  echo
}

quit() {
  local list n
  list=$(active_sessions); n=$(echo "$list" | jq 'length')
  if [ "${n:-0}" != 0 ]; then
    echo "${Y}${n} session(s) still open (EC2 costs money)${N}"
    show_sessions "$list"
    read -rp " ${Y}delete all before quitting? [Y/n]${N} " ans
    if [ "$ans" != n ]; then
      for id in $(echo "$list" | jq -r '.[].id'); do delete_session "$id"; done
    fi
  fi
  echo "${G}bye.${N}"
  exit 0
}

matrix_fx
banner
while true; do
  read -rp "${B}=>${N} " cmd || quit
  case "$cmd" in
    1) start_lab "$LAB_K8S" K8s ;;
    2) start_lab "$LAB_AWS" AWS ;;
    3) start_lab "$LAB_AUTO" AUTO ;;
    4) warm_pods ;;
    5) sessions ;;
    6) terminate ;;
    7) scheduler ;;
    r|R) banner; continue ;;
    q|Q) quit ;;
    h|H|"?") menu; continue ;;
    "") continue ;;
    *) echo " ${Y}unknown command '$cmd' (h = help)${N}" ;;
  esac
  echo "${D}$(line 78)${N}"
  menu
done
