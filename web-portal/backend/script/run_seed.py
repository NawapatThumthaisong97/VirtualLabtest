#!/usr/bin/env python3
"""
Run database seeding script
ใช้เพื่อ seed ข้อมูลตัวอย่างลงฐานข้อมูล
"""

import sys
from pathlib import Path
from sqlalchemy.orm import Session

# เพิ่ม backend folder ไปที่ sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.configs.db import SessionLocal
from app.seeds.seed import seed_database


def main():
    db: Session = SessionLocal()
    try:
        seed_database(db)
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
