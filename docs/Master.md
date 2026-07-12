# Virtual-Lab — คู่มือ Provision K3s Master ด้วย Ansible

> เอกสารภายใน — ระวังการเผยแพร่ (มีการอ้างถึง credential ของ cluster)
> อัปเดต: กรกฎาคม 2026

เป้าหมาย: เปลี่ยน VM เปล่าๆ ให้กลายเป็น K3s master ที่ควบคุมจากเครื่อง control ได้
ผ่าน Tailscale — พิมพ์ในจอ VM แค่ 3 คำสั่ง ที่เหลือ Ansible ทำให้หมด

ภาพรวม 4 เฟส:

| เฟส | ทำที่ไหน | ทำอะไร | ทำกี่ครั้ง |
|---|---|---|---|
| A | จอ VM | ลง SSH + Tailscale (bootstrap) | ครั้งเดียวต่อเครื่อง |
| B | เครื่อง control | ชี้ Ansible ไปหา VM | ครั้งเดียวต่อเครื่อง |
| C | เครื่อง control | รัน playbook ลง K3s | ซ้ำได้ไม่จำกัด |
| D | เครื่อง control | รับ kubeconfig มาใช้ + ตรวจงาน | ครั้งเดียว |

---

## เฟส A — Bootstrap ตัว VM (ทำมือ ครั้งเดียวต่อเครื่อง)

Automation ผ่าน SSH มันลง SSH ให้ตัวเองไม่ได้ (ปัญหาไก่กับไข่) เลยต้องพิมพ์ใน
console ของ VM เอง 3 คำสั่ง — **นี่คือครั้งเดียวที่ต้องพิมพ์ในจอ VM**

```bash
sudo apt update && sudo apt install -y curl openssh-server
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up        # จะได้ลิงก์ให้เปิด browser login เข้า tailnet
```

จดค่า 2 ตัวไว้ใช้เฟส B:

```bash
tailscale ip -4          # → เช่น 100.80.33.50
whoami                   # → เช่น vboxuser
```

> **ลดขั้นตอนลงอีกได้:** พอถึงช่วงทำ workers หลายเครื่อง ให้ gen **reusable auth key**
> จาก Tailscale admin console แล้วเปลี่ยนบรรทัด login เป็น
> `sudo tailscale up --authkey=tskey-…` (ไม่ต้องเปิด browser) หรือ clone จาก
> VM template ที่ bootstrap ไว้แล้ว — ต้นทุนต่อเครื่องจะเข้าใกล้ศูนย์

---

## เฟส B — ชี้ automation ไปหา VM (บนเครื่อง control)

### B.0 เช็คว่ามี SSH key หรือยัง 

`ssh-copy-id` คือการ "เอา public key **ที่มีอยู่แล้ว** ไปวางบน VM" — ถ้าเครื่อง control
ยังไม่เคยสร้าง key จะเจอ error `No identities found` ทันที เช็คก่อน:

```bash
ls ~/.ssh/id_*.pub       # มีไฟล์ = มี key แล้ว ข้ามไป B.1 ได้
ssh-keygen -t ed25519    # ถ้าไม่มี — กด Enter รัวๆ ใช้ค่า default ได้เลย
```

เงื่อนไขอื่นที่ต้องจริงก่อน ssh-copy-id จะผ่าน (ปกติผ่านอยู่แล้วถ้าทำเฟส A ครบ):
- `openssh-server` บน VM รันอยู่ (เฟส A ลงไว้แล้ว)
- tailnet ถึงกัน — ลอง `ping 100.80.33.50` หรือ `tailscale status` ดูว่าเห็น VM

### B.1 วาง key + แก้ inventory

1. แก้ `k3s-Master/inventory.yml` → ตั้ง `ansible_host:` เป็น IP จากเฟส A
2. วาง key (จะถามรหัสผ่านของ user บน VM **ครั้งเดียวครั้งสุดท้าย**):

```bash
ssh-copy-id vboxuser@100.80.33.50
```

3. ตรวจว่า Ansible คุยกับ VM ได้ — ต้องเห็น `"ping": "pong"` สีเขียว:

```bash
cd k3s-Master
ansible all -i inventory.yml -m ping -u vboxuser
```

---

## เฟส C — Provision (บนเครื่อง control)

อยากซ้อมก่อนก็เติม `--check` ท้ายคำสั่งได้ (โหมดซ้อม — task ที่เป็น shell
อาจรายงานเพี้ยนบ้าง เป็นเรื่องปกติของ check mode)

รันจริง — **BECOME password = รหัส sudo ของ user บน VM** ใช้เวลา 2–4 นาที
task `Wait for K3s API` จะค้างพักนึงระหว่าง K3s boot อันนี้ตั้งใจ ไม่ใช่แฮงค์:

```bash
ansible-playbook -i inventory.yml site.yml -u vboxuser -K
```

เกณฑ์ผ่าน: `PLAY RECAP` จบด้วย `failed=0`
บน VM สดๆ คาดหวังประมาณ `changed≈8, skipped=1` (ที่ skip คือ task ลง Tailscale
เพราะเฟส A ลงไปแล้ว — ระบบตรวจเจอเลยข้าม)

---

## เฟส D — รับ credential มาใช้ + ตรวจงาน (บนเครื่อง control)

1. kubeconfig ที่ดึงมาชี้ API เป็น `127.0.0.1` (ถูกบน VM แต่ผิดบนเครื่องเรา)
   แก้เป็น Tailscale IP:

```bash
sed -i 's/127.0.0.1/100.80.33.50/' ./artifacts/kubeconfig
```

2. ติดตั้งเป็น config หลักแล้วลองสั่งงานระยะไกล:

```bash
mkdir -p ~/.kube && cp ./artifacts/kubeconfig ~/.kube/config
chmod 600 ~/.kube/config
kubectl get nodes -o wide
```

คาดหวัง: node ของ VM สถานะ `Ready`, `INTERNAL-IP` = Tailscale IP

3. ถ้าเครื่อง control เคยเป็น cluster มาก่อน ให้ถอนทิ้งกันงง split-brain:

```bash
sudo /usr/local/bin/k3s-uninstall.sh
```

4. commit การแก้ inventory — และ**เช็คว่า `git status` ไม่มีอะไรใต้ `artifacts/`**
   (kubeconfig กับ node-token คือกุญแจ cluster ห้ามขึ้น GitHub เด็ดขาด) แล้วค่อย push

---

## 6. ตรวจสุขภาพ + งาน day-2

### 6.1 Health checks

```bash
kubectl get nodes -o wide   # node Ready; INTERNAL-IP = Tailscale IP
kubectl get pods -A         # coredns, traefik, metrics-server,
                            # local-path-provisioner ต้อง Running ครบ
```

> ถ้า `INTERNAL-IP` โชว์เป็น LAN address แทนที่จะเป็น `100.x` แปลว่า flannel
> ไม่ได้ bind กับ tailscale0 — กลับไปเช็ค `--node-ip` / `--flannel-iface`
> ให้เรียบร้อย**ก่อน**เพิ่ม workers ไม่งั้นแผล CIDR เดิมจะกลับมา

### 6.2 อ่านผล playbook ยังไง

| สถานะ | ความหมาย |
|---|---|
| `ok` (เขียว) | สภาพที่ต้องการเป็นจริงอยู่แล้ว หรือเป็น task อ่านอย่างเดียว — ไม่แตะอะไร |
| `changed` (เหลือง) | task แก้อะไรบางอย่างบนเครื่อง — playbook ที่ idempotent รันรอบสองพวกนี้ควรกลายเป็นเขียวเกือบหมด |
| `skipped` | เงื่อนไข `when:` เป็นเท็จ (เช่น Tailscale มีอยู่แล้ว) — ตั้งใจข้าม |
| `failed` (แดง) | หยุดรันทันที — อ่าน message ของ task นั้นก่อน มันบอกชื่อ module และ host ที่พัง |

---
