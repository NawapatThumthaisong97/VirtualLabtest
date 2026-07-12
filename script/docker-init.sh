#!/bin/bash

#All or noting constraints
set -e
set -o pipefail

#รับ parameter -r = build แล้ว rollback ทันทีเพื่อทดสอบ (ไม่ push จริง)
DRY_RUN=0
if [ "$1" = "-r" ]; then
  DRY_RUN=1
fi

#Error Box function
print_error_box() {
  msg="| Error : $1"
  line=$(printf '%*s' "${#msg}" '' | tr ' ' '-')
  echo "$line"
  echo "$msg"
  echo "$line"
}

rollback() {
  for img in $BUILT_IMAGES; do
   docker rmi -f "$img"
  done
  echo "All image is rolled back -> undo"
}

trap 'rollback; print_error_box "Error is happend at line : $LINENO"; exit 1' ERR

# ตรวจว่ามี repository หรือ ยังถ้ามีไม่ต้อง clone

if [ -d "music_lab" ]; then
 echo "music_lab is already exist -> bypass repository cloning"
else
 git clone "https://github.com/Petewresker/music_lab.git"
fi

cd "music_lab" || { echo "Can't enter folder -> Stopped"; exit 1; }

pwd

#ตรวจว่า port localhost 5001 ที่ seting ไว้ของ docker private เปิดแล้ว?

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5001/v2/_catalog")

if [ "$STATUS" != "200" ]; then
 echo "Can't connect to localhost:5001 (HTTP $STATUS) -> Stopped"
 exit 1
else
 echo "Connected to localhost:5001 (HTTP $STATUS) -> Proceedsing"
fi

#ตรวจว่ามีอะไรค้างอยู่บน docker ไหม ถ้าใช้ ให้ลบ image ออกตามที่กําหนด
CATALOG=$(curl -s localhost:5001/v2/_catalog | python3 -c "import sys,json; print(json.load(sys.stdin).get('repositories') or '')")

if [ -n "$CATALOG" ]; then
  for repo in $(curl -s localhost:5001/v2/_catalog | python3 -c "import sys,json; print('\n'.join(json.load(sys.stdin)['repositories']))"); do
    for tag in $(curl -s localhost:5001/v2/$repo/tags/list | python3 -c "import sys,json; print('\n'.join(json.load(sys.stdin).get('tags') or []))"); do
      digest=$(curl -s -H "Accept: application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json" \
        -I localhost:5001/v2/$repo/manifests/$tag | grep -i docker-content-digest | awk '{print $2}' | tr -d '\r' || true)

      if [ -z "$digest" ]; then
        echo "ข้าม $repo:$tag (ไม่พบ digest -> อาจถูกลบไปแล้วจาก tag อื่นที่ชี้ manifest เดียวกัน)"
        continue
      fi

      echo "ลบ $repo:$tag"
      curl -s -X DELETE localhost:5001/v2/$repo/manifests/$digest -o /dev/null -w "  -> HTTP %{http_code}\n"
    done
  done

  docker exec camp-registry bin/registry garbage-collect /etc/docker/registry/config.yml
  docker exec camp-registry sh -c "rm -rf /var/lib/registry/docker/registry/v2/repositories/camp"
  echo "Repository deleted"
else
  echo "No repositories found -> skip"
fi

#Dockerize building
TAG=lab-01

#Image Builed list สําหรับ roll back หากมีข้อผิดพลาด
BUILT_IMAGES=""

#Docker build list
docker build -t localhost:5001/camp/app-server:$TAG ./server
BUILT_IMAGES="$BUILT_IMAGES localhost:5001/camp/app-server:$TAG"

docker build -t localhost:5001/camp/app-client:$TAG --target dev ./client
BUILT_IMAGES="$BUILT_IMAGES localhost:5001/camp/app-client:$TAG"

docker build -t localhost:5001/camp/app-ide:$TAG ./ide
BUILT_IMAGES="$BUILT_IMAGES localhost:5001/camp/app-ide:$TAG"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "-r ระบุมา -> build ผ่านหมดแล้ว ทดสอบ rollback โดยไม่ push จริง"
  rollback
  exit 0
fi

#Docker push list
docker push localhost:5001/camp/app-server:$TAG

docker push localhost:5001/camp/app-client:$TAG

docker push localhost:5001/camp/app-ide:$TAG

#Check that repository is already building up or not
curl -s localhost:5001/v2/_catalog | python3 -m json.tool
