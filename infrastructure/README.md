# infrastructure

Cloud & Network Infrastructure as Code + Day-0 Bootstrap Scripts

## Purpose
Everything a Platform Engineer runs **once** (Day-0) to prepare the environment before any application deployment. After Day-0 is complete, all runtime operations are handled automatically by SkyPilot.

## Structure

```
terraform/
  vpc.tf                    ← VPC (10.0.0.0/16), Public Subnet, Private Subnet, IGW
  nat_gateway.tf            ← NAT Gateway in Public Subnet (Spot workers' internet path)
  s3_endpoint.tf            ← S3 VPC Gateway Endpoint (keeps S3 traffic on AWS backbone)
  tailscale_gateway.tf      ← t4g.nano EC2 in ASG (Min=1, Max=1) + UserData script ref
  iam.tf                    ← IAM user + policy: ec2:* (VPC scope) + s3:Get/Put (bucket scope)
  variables.tf              ← Input: region, VPC CIDR, subnet CIDRs, bucket name, TS auth key
  outputs.tf                ← Output: subnet IDs, NAT GW IP, t4g.nano instance profile ARN

cloudflare/
  tunnel.yaml               ← cloudflared ingress: routes public hostname to NGINX Service

scripts/
  bootstrap-gateway.sh      ← EC2 UserData for t4g.nano:
                               1. Install tailscale
                               2. tailscale up --advertise-routes=<VPC_CIDR>
                               3. Enable IP forwarding (net.ipv4.ip_forward=1)
  validate-network.sh       ← Smoke test: ping worker private IP from on-prem via Tailscale
  create-k8s-secrets.sh     ← Reference script for: kubectl create secret generic aws-credentials
                               ⚠️  Review before running. NEVER commit output to git.
```

## Day-0 Execution Order

```
1. terraform init && terraform apply
   └─► Creates: VPC, Subnets, NAT GW, S3 Endpoint, t4g.nano ASG, IAM user

2. Approve Tailscale subnet route in Tailscale Admin Panel
   └─► Allows 10.0.0.0/16 to be routed through the t4g.nano gateway

3. bash scripts/validate-network.sh
   └─► Verifies: On-Prem → 10.0.x.x (private IP) reachable via Tailscale

4. bash scripts/create-k8s-secrets.sh
   └─► Creates: kubectl secret aws-credentials in virtuallab namespace

5. helm upgrade --install virtuallab ../../k8s-helm -f ../../k8s-helm/values.yaml -n virtuallab
   └─► Deploys: All Control Plane pods (requires Step 4 to be complete first)
```

## Terraform Resource Map

| File | AWS Resources Created |
|:-----|:----------------------|
| `vpc.tf` | `aws_vpc`, `aws_subnet` (public + private), `aws_internet_gateway`, route tables |
| `nat_gateway.tf` | `aws_eip`, `aws_nat_gateway`, private subnet route → NAT GW |
| `s3_endpoint.tf` | `aws_vpc_endpoint` (Gateway type, S3 service) |
| `tailscale_gateway.tf` | `aws_launch_template`, `aws_autoscaling_group` (min=1, max=1), Security Group |
| `iam.tf` | `aws_iam_user`, `aws_iam_policy` (minimum permissions), `aws_iam_access_key` |

## Constraint Reminders
- ✅ Private Subnet: `map_public_ip_on_launch = false` — Spot workers get NO public IP (Constraint #4)
- ✅ t4g.nano is On-Demand (not Spot) — persistent connectivity guaranteed (Constraint #6)
- ✅ NAT Gateway: Spot workers reach Docker Hub directly, not through VPN (Constraint #7)
- ✅ S3 VPC Endpoint: S3 traffic stays on AWS backbone — no internet, no NAT GW charges (Constraint #7)
- ✅ IAM policy is scoped to minimum permissions — no AdministratorAccess (Constraint #8)
- ✅ `create-k8s-secrets.sh` is a reference/helper only — IAM keys are NEVER stored in git (Constraint #8)
