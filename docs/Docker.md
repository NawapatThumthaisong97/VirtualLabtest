# Docker

## Basic Docker

```dockerfile
FROM node:20-slim
WORKDIR /app
COPY . .
RUN npm install
CMD ["npm", "run", "dev"]
```

ข้างบนคือ docker แบบทั่วไป ถ้ามีแบบ IDE ตัวนี้คือ Multistage Docker
เพื่อให้ Container IDE สามารถแก้ไฟล์จริง ๆ ได้ที่ container อีกอัน
ซึ่ง IDE server กับ client mount volume ตัวเดียวกัน ทำให้สามารถ mount ได้

## Delete -> Build/Push ไปที่ Private Registry

ขั้นตอนการลบของเดิมแล้ว build/push ขึ้น private registry (รองรับ cache)

```bash
cd /home/pete/document/VirtualLabtest/music-lab
```

### 1) ลบ repo เดิมทั้งหมดในคลัง

```bash
for repo in $(curl -s localhost:5001/v2/_catalog | python3 -c "import sys,json; print('\n'.join(json.load(sys.stdin)['repositories']))"); do
  for tag in $(curl -s localhost:5001/v2/$repo/tags/list | python3 -c "import sys,json; print('\n'.join(json.load(sys.stdin).get('tags') or []))"); do
    digest=$(curl -s -H "Accept: application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json" \
      -I localhost:5001/v2/$repo/manifests/$tag | grep -i docker-content-digest | awk '{print $2}' | tr -d '\r')
    echo "ลบ $repo:$tag"
    curl -s -X DELETE localhost:5001/v2/$repo/manifests/$digest -o /dev/null -w "  -> HTTP %{http_code}\n"
  done
done

docker exec camp-registry bin/registry garbage-collect /etc/docker/registry/config.yml
docker exec camp-registry sh -c "rm -rf /var/lib/registry/docker/registry/v2/repositories/camp"
```

### 2) ตั้ง tag ที่จะใช้

```bash
TAG=lab-01
```

### 3) Build ทั้ง 3 ตัว

```bash
docker build -t localhost:5001/camp/app-server:$TAG ./server
docker build -t localhost:5001/camp/app-client:$TAG --target dev ./client
docker build -t localhost:5001/camp/app-ide:$TAG ./ide
```

### 4) Push ทั้ง 3 ตัว

```bash
docker push localhost:5001/camp/app-server:$TAG
docker push localhost:5001/camp/app-client:$TAG
docker push localhost:5001/camp/app-ide:$TAG
```

### 5) เช็คผล

```bash
curl -s localhost:5001/v2/_catalog | python3 -m json.tool
```
