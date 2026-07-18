#!/usr/bin/env python3
"""
Initialize database - create all tables
ใช้เพื่อสร้าง tables ทั้งหมดจากไฟล์ models
"""

import sys
from pathlib import Path

# เพิ่ม backend folder ไปที่ sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.configs.db import Base, engine
from app import models  # import ทุก models


def init_database():
    print("🔧 Initializing database...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully!")
    print("\n📊 Tables created:")
    print("  - users")
    print("  - courses")
    print("  - enrollments")
    print("  - labs")
    print("  - lab_images")
    print("  - lab_progress")
    print("  - sessions")
    print("  - usage_records")
    print("  - quotas")
    print("  - announcements")


if __name__ == "__main__":
    init_database()
