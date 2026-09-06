"""
Seed ข้อมูลตั้งต้นให้ตรง persona "Sophia Davis"

เรื่องที่ seed ชุดนี้ต้องเล่าให้ครบ:
    Sophia ล็อกอิน -> เห็นเฉพาะ 2 วิชาที่ตัวเองลง (SE301, DEVOPS201)
    -> เข้า Software Engineer เห็นเอกสาร + ประกาศจากอาจารย์
    -> เปิด lab "OOP with Spring Boot" อ่าน instruction ที่เป็น PDF จริง

จุดที่พลาดกันบ่อย 2 อย่าง:

1. lab UUID ของ SE301 ถูก hardcode ไว้ (ไม่ใช่ uuid4()) เพราะไฟล์ PDF วางอยู่
   ที่ storage/labs/{lab_id}/doc.pdf บน disk อยู่แล้ว ถ้าสุ่ม id ใหม่ทุกครั้ง
   doc_url จะชี้ไปโฟลเดอร์ที่ไม่มีไฟล์ แล้วหน้า lab จะขึ้น 404 ตลอด

   storage/** ถูก gitignore ไว้ ไฟล์ PDF เลยไม่ติดมากับ repo — เครื่องใหม่ต้อง
   วางไฟล์เองก่อน (ต้นฉบับ commit ไว้ที่ script/assets/):
       python script/setup_lab_doc.py script/assets/OOP_SpringBoot_workbook.pdf \
           --lab-id 03a18386-1558-4bcf-9399-4b79cc1ae22b

2. CS102 ใส่ไว้ตั้งใจให้ Sophia "ไม่ได้" ลงเรียน — เอาไว้พิสูจน์ว่า
   GET /api/courses กรองตามคนล็อกอินจริง ไม่ใช่คืนทุกวิชาในระบบ
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.announcement import Announcement
from app.models.courses import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab, LabStatus
from app.models.lab_image import ImageStatus, LabImage
from app.models.lab_progress import LabProgress, ProgressStatus
from app.models.quota import Quota, QuotaPeriod
from app.models.session import ServiceType, Session as ComputeSession, SessionStatus
from app.models.usage_record import UsageRecord
from app.models.user import User, UserRole
from app.utils.security import hash_password

# รหัสผ่านของ staff กับนักศึกษาคนอื่น — ของ Sophia แยกต่างหากข้างล่าง
SEED_PASSWORD = "labpass123"
SOPHIA_PASSWORD = "sophia6764"

# ผูกกับไฟล์ที่มีอยู่จริงใน storage/labs/<id>/doc.pdf — ห้ามสุ่มใหม่
LAB_OOP_ID = uuid.UUID("03a18386-1558-4bcf-9399-4b79cc1ae22b")
LAB_POLYMORPHISM_ID = uuid.UUID("213f2122-1e9f-465c-8602-87c1a6985017")


def seed_database(db: Session):
    """Seed ข้อมูลตัวอย่างลงฐานข้อมูล"""

    # 1. ตรวจสอบว่าข้อมูลมีแล้วหรือไม่
    if db.query(User).first():
        print("[!] Database already seeded. Skipping...")
        print("    ยังไม่มี Alembic ในโปรเจกต์ ถ้าจะ seed ใหม่ต้อง drop DB ก่อน:")
        print(
            "    docker exec virtual_lab_db psql -U postgres "
            '-c "DROP DATABASE virtual_lab;" -c "CREATE DATABASE virtual_lab;"'
        )
        print("    แล้วรัน script/init_db.py ตามด้วย script/run_seed.py")
        return

    print("[*] Seeding database...")

    # 2. สร้าง Users
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@dome.tu.ac.th",
        name="Virtual Lab Admin",
        password_hash=hash_password(SEED_PASSWORD),
        role=UserRole.ADMIN,
    )

    se_instructor = User(
        id=uuid.uuid4(),
        email="kittipong.som@dome.tu.ac.th",
        name="Dr. Kittipong Somsak",
        password_hash=hash_password(SEED_PASSWORD),
        role=UserRole.INSTRUCTOR,
    )

    devops_instructor = User(
        id=uuid.uuid4(),
        email="marisa.chan@dome.tu.ac.th",
        name="Dr. Marisa Chandra",
        password_hash=hash_password(SEED_PASSWORD),
        role=UserRole.INSTRUCTOR,
    )

    # persona หลักของรอบนี้
    sophia = User(
        id=uuid.uuid4(),
        email="sophia.dav@dome.tu.ac.th",
        name="Sophia Davis",
        student_id="6709616000",
        password_hash=hash_password(SOPHIA_PASSWORD),
        role=UserRole.STUDENT,
    )

    # นักศึกษาอีกคนที่ลงวิชาที่ Sophia ไม่ได้ลง — ใช้เช็คว่า filter ทำงาน
    nathan = User(
        id=uuid.uuid4(),
        email="nathan.col@dome.tu.ac.th",
        name="Nathan Cole",
        student_id="6709616001",
        password_hash=hash_password(SEED_PASSWORD),
        role=UserRole.STUDENT,
    )

    db.add_all([admin_user, se_instructor, devops_instructor, sophia, nathan])
    db.commit()
    print("[ok] Created 5 users")

    # 3. สร้าง Courses
    se_course = Course(
        id=uuid.uuid4(),
        code="SE301",
        name="Software Engineer",
        lecturer_name=se_instructor.name,
        background_key="blue3",
        icon_key="database",
        created_by=se_instructor.id,
    )

    devops_course = Course(
        id=uuid.uuid4(),
        code="DEVOPS201",
        name="DevOps",
        lecturer_name=devops_instructor.name,
        background_key="blue2",
        icon_key="layers",
        created_by=devops_instructor.id,
    )

    # วิชาที่ Sophia ไม่ได้ลง — ต้องไม่โผล่ในหน้า /courses ของเธอ
    other_course = Course(
        id=uuid.uuid4(),
        code="CS102",
        name="Data Structures",
        lecturer_name="Prof. Jose Matt",
        background_key="blue1",
        icon_key="cloud",
        created_by=admin_user.id,
    )

    db.add_all([se_course, devops_course, other_course])
    db.commit()
    print("[ok] Created 3 courses (Sophia ลง 2, CS102 เป็นตัวคุมสำหรับเช็ค filter)")

    # 4. สร้าง Enrollments
    db.add_all(
        [
            Enrollment(
                user_id=sophia.id,
                course_id=se_course.id,
                role_in_course=RoleInCourse.STUDENT,
            ),
            Enrollment(
                user_id=sophia.id,
                course_id=devops_course.id,
                role_in_course=RoleInCourse.STUDENT,
            ),
            Enrollment(
                user_id=se_instructor.id,
                course_id=se_course.id,
                role_in_course=RoleInCourse.INSTRUCTOR,
            ),
            Enrollment(
                user_id=devops_instructor.id,
                course_id=devops_course.id,
                role_in_course=RoleInCourse.INSTRUCTOR,
            ),
            Enrollment(
                user_id=nathan.id,
                course_id=other_course.id,
                role_in_course=RoleInCourse.STUDENT,
            ),
        ]
    )
    db.commit()
    print("[ok] Created 5 enrollments")

    # 5. สร้าง Lab Images
    # image เดียวในโปรเจกต์ที่ build แล้วและ push ขึ้น registry จริง
    # ค่าทุกตัวข้างล่างล็อกตาม music-lab/skypilot/task.yaml — ห้ามแก้ให้ต่าง
    # ไม่งั้น session ที่ launch จะเปิด port ไม่ตรงกับที่ image รันจริง
    se_image = LabImage(
        id=uuid.uuid4(),
        uploaded_by=se_instructor.id,
        course_id=se_course.id,
        repository="skypilot/music-lab",
        tag="lab-01",
        image_digest="sha256:1f0c9a72",
        size_mb=640,
        status=ImageStatus.APPROVED,
        cpu_requirement="2+",
        memory_requirement="4+",
        disk_size=50,
        lifespan_minutes=60,
        # ต้องตรงกับ endpoints ของ running_session ข้างล่าง
        exposed_ports=[8080, 5173, 8443],
        entrypoint_script="/bin/bash /run.sh",
        workdir=None,
        env_vars={
            "IDE_PASSWORD": "musiclab",
            "DATA_DIR": "/data",
            "MUSIC_DIR": "/data/music",
        },
        description="All-in-one lab: Flask API (8080), Vite client (5173), code-server IDE (8443)",
    )

    # ยังไม่มี image จริงรองรับ (มีแค่ music-lab ตัวเดียวในโปรเจกต์)
    # ปล่อยชื่อ placeholder ไว้ก่อน แต่กรอกคอลัมน์ใหม่ให้ครบกัน default ว่างเปล่า
    devops_image = LabImage(
        id=uuid.uuid4(),
        uploaded_by=devops_instructor.id,
        course_id=devops_course.id,
        repository="vlab/devops-toolbox",
        tag="devops201-lab01",
        image_digest="sha256:8b45de10",
        size_mb=980,
        status=ImageStatus.APPROVED,
        cpu_requirement="2+",
        memory_requirement="4+",
        disk_size=30,
        lifespan_minutes=60,
        exposed_ports=[3000],
        entrypoint_script="/bin/bash /entrypoint.sh",
        workdir=None,
        env_vars={"NODE_ENV": "development"},
        description="DevOps toolbox (ยังไม่ได้ build image จริง)",
    )

    db.add_all([se_image, devops_image])
    db.commit()
    print("[ok] Created 2 lab images")

    # 6. สร้าง Labs
    # SE301 คือวิชาที่ persona เดินเข้า — ต้องสมบูรณ์ที่สุด และเป็นวิชาเดียว
    # ที่มี doc_url เพราะไฟล์ PDF มีอยู่จริงแค่ 2 ไฟล์บน disk
    oop_lab = Lab(
        id=LAB_OOP_ID,
        course_id=se_course.id,
        title="OOP with Spring Boot",
        order_no=1,
        description=(
            "สร้าง class hierarchy ของระบบยืม-คืนหนังสือ แล้วใช้ inheritance "
            "กับ polymorphism ให้ครบตามที่โจทย์กำหนด"
        ),
        doc_url=f"labs/{LAB_OOP_ID}/doc.pdf",
        image_id=se_image.id,
        due_at=datetime.utcnow() + timedelta(days=14),
        status=LabStatus.PUBLISHED,
    )

    polymorphism_doc = Lab(
        id=LAB_POLYMORPHISM_ID,
        course_id=se_course.id,
        title="Unit 5 : Polymorphism (reading)",
        order_no=2,
        description="เอกสารประกอบก่อนเข้าคาบ — อ่านก่อนทำ lab ถัดไป",
        doc_url=f"labs/{LAB_POLYMORPHISM_ID}/doc.pdf",
        image_id=None,
        due_at=None,
        status=LabStatus.PUBLISHED,
    )

    # DevOps — mock ไว้ให้หน้าตาไม่โล่ง ยังไม่มีเอกสารจริง
    devops_labs = [
        Lab(
            id=uuid.uuid4(),
            course_id=devops_course.id,
            title="CI/CD Pipeline with GitHub Actions",
            order_no=1,
            description="ต่อ pipeline ให้ build + test + push image อัตโนมัติ",
            image_id=devops_image.id,
            due_at=datetime.utcnow() + timedelta(days=10),
            status=LabStatus.PUBLISHED,
        ),
        Lab(
            id=uuid.uuid4(),
            course_id=devops_course.id,
            title="Containerize a Node.js App",
            order_no=2,
            description="เขียน Dockerfile แล้วลดขนาด image ด้วย multi-stage build",
            due_at=datetime.utcnow() + timedelta(days=21),
            status=LabStatus.PUBLISHED,
        ),
        Lab(
            id=uuid.uuid4(),
            course_id=devops_course.id,
            title="Kubernetes Basics",
            order_no=3,
            description="ยังไม่เปิดให้นักศึกษา",
            status=LabStatus.DRAFT,
        ),
    ]

    other_lab = Lab(
        id=uuid.uuid4(),
        course_id=other_course.id,
        title="Linked List & Stack",
        order_no=1,
        status=LabStatus.PUBLISHED,
    )

    db.add_all([oop_lab, polymorphism_doc, *devops_labs, other_lab])
    db.commit()
    print("[ok] Created 6 labs")

    # 7. สร้าง Lab Progress
    db.add_all(
        [
            LabProgress(
                user_id=sophia.id,
                lab_id=oop_lab.id,
                status=ProgressStatus.IN_PROGRESS,
                started_at=datetime.utcnow() - timedelta(hours=1),
            ),
            LabProgress(
                user_id=sophia.id,
                lab_id=devops_labs[0].id,
                status=ProgressStatus.NOT_STARTED,
            ),
        ]
    )
    db.commit()
    print("[ok] Created 2 lab progress records")

    # 8. สร้าง Sessions
    # session นี้ทำให้ "lab ถูก launch ไว้อยู่แล้ว" ตาม persona เป็นจริงได้
    # โดยไม่ต้องมี K8s — endpoints ครบทั้ง 3 ตัวรอหน้า Lab Hub มาอ่านทีหลัง
    running_session = ComputeSession(
        id=uuid.uuid4(),
        user_id=sophia.id,
        lab_id=oop_lab.id,
        service_type=ServiceType.LAB,
        k8s_pod_name="lab-se301-sophia",
        node_name="node-01",
        is_remote=False,
        is_cloud=False,
        lab_image_id=se_image.id,
        endpoints={
            "ide": "http://localhost:8443",
            "client": "http://localhost:5173",
            "server": "http://localhost:8080",
        },
        status=SessionStatus.RUNNING,
        started_at=datetime.utcnow() - timedelta(minutes=45),
        expires_at=datetime.utcnow() + timedelta(hours=2),
    )

    db.add(running_session)
    db.commit()
    print("[ok] Created 1 running session")

    # 9. สร้าง Usage Records
    db.add(
        UsageRecord(
            session_id=running_session.id,
            cpu_seconds=2700,
            gpu_seconds=0,
            ram_mb_hours=1536,
            is_cloud_burst=False,
            est_cost_thb=18.5,
        )
    )
    db.commit()
    print("[ok] Created 1 usage record")

    # 10. สร้าง Quotas
    db.add_all(
        [
            Quota(
                id=uuid.uuid4(),
                user_id=sophia.id,
                course_id=None,
                compute_hours_limit=50.0,
                storage_mb_limit=10240,
                period=QuotaPeriod.MONTHLY,
            ),
            Quota(
                id=uuid.uuid4(),
                user_id=None,
                course_id=se_course.id,
                compute_hours_limit=500.0,
                storage_mb_limit=102400,
                period=QuotaPeriod.SEMESTER,
            ),
        ]
    )
    db.commit()
    print("[ok] Created 2 quotas")

    # 11. สร้าง Announcements
    db.add_all(
        [
            Announcement(
                id=uuid.uuid4(),
                course_id=se_course.id,
                author_id=se_instructor.id,
                message=(
                    "Today I suggest you to read unit 5 polymorphism "
                    "before you take a class"
                ),
            ),
            Announcement(
                id=uuid.uuid4(),
                course_id=se_course.id,
                author_id=se_instructor.id,
                message="Lab 1 (OOP with Spring Boot) is open — deadline in 2 weeks.",
            ),
            Announcement(
                id=uuid.uuid4(),
                course_id=devops_course.id,
                author_id=devops_instructor.id,
                message="Bring your own GitHub account to the next lab session.",
            ),
        ]
    )
    db.commit()
    print("[ok] Created 3 announcements")

    print("\n[done] Database seeding completed successfully!")
    print("\nSummary:")
    print(f"  - Users: {db.query(User).count()}")
    print(f"  - Courses: {db.query(Course).count()}")
    print(f"  - Enrollments: {db.query(Enrollment).count()}")
    print(f"  - Labs: {db.query(Lab).count()}")
    print(f"  - Lab Images: {db.query(LabImage).count()}")
    print(f"  - Lab Progress: {db.query(LabProgress).count()}")
    print(f"  - Sessions: {db.query(ComputeSession).count()}")
    print(f"  - Usage Records: {db.query(UsageRecord).count()}")
    print(f"  - Quotas: {db.query(Quota).count()}")
    print(f"  - Announcements: {db.query(Announcement).count()}")
    print("\nLogin ด้วย persona:")
    print(f"  student_id : {sophia.student_id}")
    print(f"  email      : {sophia.email}")
    print(f"  password   : {SOPHIA_PASSWORD}")
