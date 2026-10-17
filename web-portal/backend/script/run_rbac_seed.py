#!/usr/bin/env python3
"""Seed RBAC roles and permissions without replacing the application seed data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.configs.db import SessionLocal
from app.seeds.rbac_seed import RBACSeeder


def main() -> None:
    db = SessionLocal()
    try:
        RBACSeeder(db).seed()
        print("RBAC roles and permissions seeded successfully.")
    except Exception as error:
        print(f"RBAC seeding failed: {error}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()