#!/bin/bash

REGISTRY=100.127.74.48:5001

# เช็คว่า repo:tag มีอยู่ใน registry แล้วหรือยัง (HTTP 200 = มีแล้ว, 404 = ยังไม่มี)
image_exists() {
  local repo="$1" tag="$2"
  # ต้องใส่ Accept ครบทุกแบบ (v2 schema2 เดี่ยว + manifest list + OCI) เพราะ docker buildx
  # เก็บ image เป็น manifest list (multi-platform) เสมอ ถ้าขอด้วย Accept แบบ v2 อย่างเดียว
  # registry จะตอบว่าไม่เจอ (content-type ไม่ตรง) ทั้งที่จริง ๆ มีอยู่แล้ว
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Accept: application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json" \
    "http://$REGISTRY/v2/${repo}/manifests/${tag}")
  [ "$status" = "200" ]
}

# build+push เฉพาะเมื่อยังไม่มี tag นี้ใน registry 
build_and_push() {
  local repo="$1" tag="$2" context="$3"
  shift 3
  if image_exists "$repo" "$tag"; then
    echo "$repo:$tag มีอยู่แล้ว -> ข้าม build/push"
  else
    docker build -t "$REGISTRY/$repo:$tag" "$@" "$context"
    docker push "$REGISTRY/$repo:$tag"
  fi
}

# skypilot/bake
build_and_push skypilot/bake 0.12.3.post1 docker/bake/ -f docker/bake/dockerfile

# skypilot/music-lab
build_and_push skypilot/music-lab lab-01 music-lab/ -f music-lab/skypilot/Dockerfile
