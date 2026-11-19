from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/")
def index():
    return """<!doctype html>
<html lang="th">
<head><meta charset="utf-8"><title>Python Web Lab</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 42rem; margin: 3rem auto; padding: 0 1rem; line-height: 1.6; }
  code { background: #f1f1f1; padding: 0.1rem 0.3rem; border-radius: 4px; }
</style></head>
<body>
  <h1>Python Web Lab</h1>
  <p>เว็บนี้รันจากไฟล์ <code>app.py</code> ใน JupyterLab (port 8888)
     แก้ไฟล์แล้วกด save หน้านี้จะเปลี่ยนตามเองหลัง reload</p>
  <ul>
    <li><a href="/hello/student">/hello/student</a></li>
    <li><a href="/square/4">/square/4</a> (แบบฝึกหัด 03 ยังไม่ได้ทำ จะได้ 404)</li>
  </ul>
</body>
</html>"""


@app.get("/hello/<name>")
def hello(name):
    return jsonify(message=f"Hello, {name}!")


# แบบฝึกหัด 03: เพิ่ม route /square/<int:n> ตรงนี้ ให้ตอบ {"n": n, "square": n * n}
