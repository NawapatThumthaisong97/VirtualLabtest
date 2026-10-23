"""Add class_schedules / class_slots (prewarm) and sessions.class_slot_id.

Revision ID: 20261013_08
Revises: 20261013_07
Create Date: 2026-10-21

ตารางเรียน + รอบเรียนที่ scheduler ใช้ pre-warm image / warm pod ก่อนคาบ (docs/archive/add-class-schedule-tables.md)
เดิมสร้างด้วย create_all อย่างเดียว — แต่ตอนนี้ sessions มาจาก migration ก่อน create_all จะรัน
create_all ไม่เติมคอลัมน์ให้ตารางที่มีอยู่แล้ว เลยขาด sessions.class_slot_id (seed พัง UndefinedColumn)

DDL เหมือนที่ create_all สร้างจาก model (app/models/class_schedule.py, class_slot.py)
IF NOT EXISTS ทุกตัว: DB ที่ create_all สร้างไว้แล้ว (dev เดิม) รันซ้ำได้
"""

from alembic import op


revision = "20261013_08"
down_revision = "20261013_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        # exclusion constraint ที่มี "=" บน uuid ต้องใช้ btree_gist
        "CREATE EXTENSION IF NOT EXISTS btree_gist",
        """DO $$ BEGIN
               CREATE TYPE classslotstatus AS ENUM ('SCHEDULED', 'PREWARMING', 'READY', 'DONE', 'CANCELLED');
           EXCEPTION WHEN duplicate_object THEN NULL;
           END $$""",
        """CREATE TABLE IF NOT EXISTS class_schedules (
            id uuid PRIMARY KEY,
            course_id uuid NOT NULL REFERENCES courses(id),
            weekday integer NOT NULL,
            start_time time without time zone NOT NULL,
            end_time time without time zone NOT NULL,
            valid_from date NOT NULL,
            valid_until date NOT NULL,
            default_lab_image_id uuid REFERENCES lab_images(id),
            expected_seats integer NOT NULL,
            created_by uuid NOT NULL REFERENCES users(id),
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            deleted_at timestamp with time zone,
            CONSTRAINT ck_class_schedules_date_order CHECK (valid_until >= valid_from),
            CONSTRAINT ck_class_schedules_seats CHECK (expected_seats > 0),
            CONSTRAINT ck_class_schedules_time_order CHECK (end_time > start_time),
            CONSTRAINT ck_class_schedules_weekday CHECK (weekday >= 0 AND weekday <= 6)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_class_schedules_course_id ON class_schedules (course_id)",
        "CREATE INDEX IF NOT EXISTS ix_class_schedules_deleted_at ON class_schedules (deleted_at)",
        "CREATE INDEX IF NOT EXISTS ix_class_schedules_id ON class_schedules (id)",
        """CREATE TABLE IF NOT EXISTS class_slots (
            id uuid PRIMARY KEY,
            schedule_id uuid REFERENCES class_schedules(id),
            course_id uuid NOT NULL REFERENCES courses(id),
            lab_id uuid REFERENCES labs(id),
            lab_image_id uuid NOT NULL REFERENCES lab_images(id) ON DELETE RESTRICT,
            starts_at timestamp with time zone NOT NULL,
            ends_at timestamp with time zone NOT NULL,
            expected_seats integer NOT NULL,
            run_target runtarget DEFAULT 'KUBERNETES'::runtarget NOT NULL,
            status classslotstatus DEFAULT 'SCHEDULED'::classslotstatus NOT NULL,
            note text,
            created_by uuid NOT NULL REFERENCES users(id),
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            deleted_at timestamp with time zone,
            CONSTRAINT ck_class_slots_seats CHECK (expected_seats > 0),
            CONSTRAINT ck_class_slots_time_order CHECK (ends_at > starts_at),
            CONSTRAINT ex_class_slots_no_overlap EXCLUDE USING gist
                (course_id WITH =, tstzrange(starts_at, ends_at) WITH &&)
                WHERE (deleted_at IS NULL AND status <> 'CANCELLED'::classslotstatus)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_course_starts_at ON class_slots (course_id, starts_at)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_deleted_at ON class_slots (deleted_at)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_id ON class_slots (id)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_schedule_id ON class_slots (schedule_id)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_starts_at ON class_slots (starts_at)",
        """ALTER TABLE sessions
           ADD COLUMN IF NOT EXISTS class_slot_id uuid REFERENCES class_slots(id) ON DELETE SET NULL""",
    )
    for stmt in statements:
        op.execute(stmt)


def downgrade() -> None:
    statements = (
        "ALTER TABLE sessions DROP COLUMN IF EXISTS class_slot_id",
        "DROP TABLE IF EXISTS class_slots",
        "DROP TABLE IF EXISTS class_schedules",
        "DROP TYPE IF EXISTS classslotstatus",
    )
    for stmt in statements:
        op.execute(stmt)
