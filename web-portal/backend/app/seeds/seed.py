import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.user import User, UserRole
from app.models.course import Course
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab, LabStatus
from app.models.lab_image import LabImage, ImageStatus
from app.models.lab_progress import LabProgress, ProgressStatus
from app.models.session import Session as ComputeSession, ServiceType, SessionStatus
from app.models.usage_record import UsageRecord
from app.models.quota import Quota, QuotaPeriod
from app.models.announcement import Announcement


def seed_database(db: Session):
    """Seed ข้อมูลตัวอย่างลงฐานข้อมูล"""
    
    # 1. ตรวจสอบว่าข้อมูลมีแล้วหรือไม่
    if db.query(User).first():
        print("⚠️  Database already seeded. Skipping...")
        return
    
    print("🌱 Seeding database...")
    
    # 2. สร้าง Users
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        name="Admin User",
        role=UserRole.ADMIN,
    )
    
    instructor_user = User(
        id=uuid.uuid4(),
        email="instructor@example.com",
        name="Dr. John Instructor",
        role=UserRole.INSTRUCTOR,
    )
    
    student1 = User(
        id=uuid.uuid4(),
        email="student1@example.com",
        name="Alice Student",
        student_id="6420001001",
        role=UserRole.STUDENT,
    )
    
    student2 = User(
        id=uuid.uuid4(),
        email="student2@example.com",
        name="Bob Student",
        student_id="6420001002",
        role=UserRole.STUDENT,
    )
    
    db.add_all([admin_user, instructor_user, student1, student2])
    db.commit()
    print(f"✅ Created {4} users")
    
    # 3. สร้าง Courses
    course1 = Course(
        id=uuid.uuid4(),
        code="CS217",
        name="Web Development",
        lecturer_name="Dr. John Instructor",
        banner_color="#FF5733",
        created_by=instructor_user.id,
    )
    
    course2 = Course(
        id=uuid.uuid4(),
        code="CS301",
        name="Machine Learning",
        lecturer_name="Dr. Jane Instructor",
        banner_color="#3366FF",
        created_by=instructor_user.id,
    )
    
    db.add_all([course1, course2])
    db.commit()
    print(f"✅ Created {2} courses")
    
    # 4. สร้าง Enrollments
    enrollment1 = Enrollment(
        user_id=student1.id,
        course_id=course1.id,
        role_in_course=RoleInCourse.STUDENT,
    )
    
    enrollment2 = Enrollment(
        user_id=student2.id,
        course_id=course1.id,
        role_in_course=RoleInCourse.STUDENT,
    )
    
    enrollment3 = Enrollment(
        user_id=instructor_user.id,
        course_id=course1.id,
        role_in_course=RoleInCourse.INSTRUCTOR,
    )
    
    db.add_all([enrollment1, enrollment2, enrollment3])
    db.commit()
    print(f"✅ Created {3} enrollments")
    
    # 5. สร้าง Lab Images
    lab_image1 = LabImage(
        id=uuid.uuid4(),
        uploaded_by=instructor_user.id,
        course_id=course1.id,
        repository="skypilot/music-lab",
        tag="lab-01",
        image_digest="sha256:abcd1234",
        size_mb=512,
        status=ImageStatus.APPROVED,
    )
    
    lab_image2 = LabImage(
        id=uuid.uuid4(),
        uploaded_by=instructor_user.id,
        course_id=course1.id,
        repository="skypilot/web-lab",
        tag="lab-02",
        image_digest="sha256:efgh5678",
        size_mb=768,
        status=ImageStatus.APPROVED,
    )
    
    db.add_all([lab_image1, lab_image2])
    db.commit()
    print(f"✅ Created {2} lab images")
    
    # 6. สร้าง Labs
    lab1 = Lab(
        id=uuid.uuid4(),
        course_id=course1.id,
        title="Lab 1: Setup Environment",
        order_no=1,
        doc_url="https://r2.example.com/labs/lab1.pdf",
        image_id=lab_image1.id,
        due_at=datetime.utcnow() + timedelta(days=7),
        status=LabStatus.PUBLISHED,
    )
    
    lab2 = Lab(
        id=uuid.uuid4(),
        course_id=course1.id,
        title="Lab 2: Build REST API",
        order_no=2,
        doc_url="https://r2.example.com/labs/lab2.pdf",
        image_id=lab_image2.id,
        due_at=datetime.utcnow() + timedelta(days=14),
        status=LabStatus.PUBLISHED,
    )
    
    lab3 = Lab(
        id=uuid.uuid4(),
        course_id=course1.id,
        title="Lab 3: Deploy to Cloud",
        order_no=3,
        doc_url="https://r2.example.com/labs/lab3.pdf",
        image_id=None,
        due_at=datetime.utcnow() + timedelta(days=21),
        status=LabStatus.DRAFT,
    )
    
    db.add_all([lab1, lab2, lab3])
    db.commit()
    print(f"✅ Created {3} labs")
    
    # 7. สร้าง Lab Progress
    lab_progress1 = LabProgress(
        user_id=student1.id,
        lab_id=lab1.id,
        status=ProgressStatus.FINISHED,
        started_at=datetime.utcnow() - timedelta(days=5),
        finished_at=datetime.utcnow() - timedelta(days=4),
    )
    
    lab_progress2 = LabProgress(
        user_id=student1.id,
        lab_id=lab2.id,
        status=ProgressStatus.IN_PROGRESS,
        started_at=datetime.utcnow() - timedelta(days=1),
        finished_at=None,
    )
    
    lab_progress3 = LabProgress(
        user_id=student2.id,
        lab_id=lab1.id,
        status=ProgressStatus.NOT_STARTED,
    )
    
    db.add_all([lab_progress1, lab_progress2, lab_progress3])
    db.commit()
    print(f"✅ Created {3} lab progress records")
    
    # 8. สร้าง Sessions
    session1 = ComputeSession(
        id=uuid.uuid4(),
        user_id=student1.id,
        lab_id=lab1.id,
        service_type=ServiceType.LAB,
        k8s_pod_name="pod-lab1-student1",
        node_name="node-01",
        is_remote=False,
        is_cloud=False,
        image_ref="skypilot/music-lab:lab-01",
        endpoints={"ide": "http://localhost:8080", "ssh": "ssh://localhost:2222"},
        status=SessionStatus.RUNNING,
        started_at=datetime.utcnow() - timedelta(hours=2),
    )
    
    session2 = ComputeSession(
        id=uuid.uuid4(),
        user_id=student1.id,
        lab_id=None,
        service_type=ServiceType.SANDBOX,
        is_remote=True,
        is_cloud=True,
        sky_cluster_name="sky-cluster-1",
        sky_job_id=12345,
        image_ref="skypilot/gpu:latest",
        status=SessionStatus.PENDING,
    )
    
    db.add_all([session1, session2])
    db.commit()
    print(f"✅ Created {2} sessions")
    
    # 9. สร้าง Usage Records
    usage1 = UsageRecord(
        session_id=session1.id,
        cpu_seconds=3600,
        gpu_seconds=0,
        ram_mb_hours=2048,
        is_cloud_burst=False,
        est_cost_thb=50.0,
    )
    
    usage2 = UsageRecord(
        session_id=session2.id,
        cpu_seconds=7200,
        gpu_seconds=3600,
        ram_mb_hours=8192,
        is_cloud_burst=True,
        est_cost_thb=250.0,
    )
    
    db.add_all([usage1, usage2])
    db.commit()
    print(f"✅ Created {2} usage records")
    
    # 10. สร้าง Quotas
    quota1 = Quota(
        id=uuid.uuid4(),
        user_id=student1.id,
        course_id=None,
        compute_hours_limit=50.0,
        storage_mb_limit=10240,
        period=QuotaPeriod.MONTHLY,
    )
    
    quota2 = Quota(
        id=uuid.uuid4(),
        user_id=None,
        course_id=course1.id,
        compute_hours_limit=500.0,
        storage_mb_limit=102400,
        period=QuotaPeriod.SEMESTER,
    )
    
    db.add_all([quota1, quota2])
    db.commit()
    print(f"✅ Created {2} quotas")
    
    # 11. สร้าง Announcements
    announcement1 = Announcement(
        id=uuid.uuid4(),
        course_id=course1.id,
        author_id=instructor_user.id,
        message="Welcome to CS217! Please read the syllabus before the first class.",
    )
    
    announcement2 = Announcement(
        id=uuid.uuid4(),
        course_id=None,
        author_id=admin_user.id,
        message="🔔 Global announcement: System maintenance on Friday, 2-4 PM UTC",
    )
    
    db.add_all([announcement1, announcement2])
    db.commit()
    print(f"✅ Created {2} announcements")
    
    print("\n✨ Database seeding completed successfully!")
    print("\n📊 Summary:")
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
