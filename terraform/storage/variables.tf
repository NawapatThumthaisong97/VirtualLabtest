variable "region" {
  type    = string
  default = "ap-southeast-1"
}

# ไม่มีค่าเริ่มต้น: ส่งทุกครั้ง (-var aws_profile=...) ไม่ให้เผลอใช้ profile skypilot ของ backend
variable "aws_profile" {
  description = "AWS CLI profile ที่มีสิทธิ์สร้าง bucket / IAM policy (ของ Pete)"
  type        = string
}

# IAM user ที่ backend ใช้อยู่แล้ว (profile skypilot ใน container) — ได้สิทธิ์เฉพาะ bucket นี้
variable "backend_iam_user" {
  type    = string
  default = "Skypilot-IAM"
}

# origin ของเว็บที่เปิด presigned URL ด้วย fetch (react-pdf อ่าน PDF) — <a> / <img> ไม่ต้องใช้ CORS
variable "web_origins" {
  type    = list(string)
  default = ["http://100.102.72.39", "http://localhost:5173"]
}

# เวอร์ชันเก่าของไฟล์ที่ถูกเขียนทับ / ลบ เก็บไว้กี่วัน (กู้ไฟล์ที่อาจารย์ลบผิดได้)
variable "noncurrent_days" {
  type    = number
  default = 30
}
