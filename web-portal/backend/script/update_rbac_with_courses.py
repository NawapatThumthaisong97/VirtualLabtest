"""
Script สำหรับอัปเดต RBAC permissions เพื่อเพิ่ม course permissions

การใช้งาน:
    cd web-portal/backend
    python script/update_rbac_with_courses.py
"""
import sys
from pathlib import Path

# เพิ่ม path ของ app เข้าไปใน sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.configs.db import SessionLocal
from app.seeds.rbac_seed import RBACSeeder


def main():
    """อัปเดต RBAC permissions เพื่อรองรับ course management"""
    print("🔄 Starting RBAC update with course permissions...")
    
    db = SessionLocal()
    try:
        seeder = RBACSeeder(db)
        seeder.seed()
        
        print("✅ RBAC update completed successfully!")
        print("\n📋 Added permissions:")
        print("   - courses:read:self")
        print("   - courses:create:self")
        print("   - courses:update:course")
        print("   - courses:delete:course")
        print("   - courses:manage:global")
        print("   - courses:announcements:create:course")
        print("   - courses:announcements:update:course")
        print("   - courses:announcements:delete:course")
        print("\n📋 Role assignments:")
        print("   Student: courses:read:self")
        print("   Instructor: courses:read:self, courses:create:self, ")
        print("               courses:update:course, courses:delete:course,")
        print("               courses:announcements:*:course")
        print("   Admin: courses:manage:global")
        
    except Exception as e:
        print(f"❌ Error updating RBAC: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
