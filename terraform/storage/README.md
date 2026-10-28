# terraform/storage — S3 bucket ของเว็บ

bucket เดียว แยกด้วย prefix (key เดิมที่ DB เก็บอยู่แล้ว):

| prefix | เก็บอะไร |
|---|---|
| `courses/<course_id>/<ไฟล์>` | รูปปกวิชาที่อัปเอง |
| `labs/<lab_id>/<ไฟล์>.pdf` | เอกสารของ lab |
| `course-docs/<course_id>/<doc_id>.pdf` | เอกสารวิชาที่ไม่ผูก lab |

```bash
cd terraform/storage
terraform init
terraform plan  -var aws_profile=<profile ของเรา>
terraform apply -var aws_profile=<profile ของเรา>
```

- state อยู่ในเครื่อง (`terraform.tfstate` ถูก gitignore) — **สำรองไว้** ไม่งั้นรอบหน้าจะสร้างซ้ำ
- backend ใช้ IAM user `Skypilot-IAM` เดิม ได้ policy `vlab-web-storage` (อ่าน / เขียน / ลบ เฉพาะ bucket นี้)
- private ทั้งหมด เปิดไฟล์ผ่าน presigned URL ที่ backend ออกหลังเช็กสิทธิ์
