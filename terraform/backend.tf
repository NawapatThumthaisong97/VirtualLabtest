# state เก็บใน S3 แทนเครื่องคนใดคนหนึ่ง ให้ Pete กับทีม plan/apply ได้จากเครื่องตัวเอง
# bucket สร้างด้วยมือ (private + versioning + SSE) ไม่อยู่ใน terraform นี้ กันลบ state ตัวเอง
# use_lockfile = ล็อกด้วยไฟล์ .tflock ใน S3 (Terraform >= 1.10) สองคน apply พร้อมกันไม่ได้
# profile ไม่ใส่ที่นี่ แต่ละคนส่งเอง: terraform init -backend-config="profile=<ชื่อ profile>"
terraform {
  backend "s3" {
    bucket       = "vlab-tfstate-568318158381"
    key          = "aws/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
