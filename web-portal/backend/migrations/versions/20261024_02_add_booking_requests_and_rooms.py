"""booking_requests + room ใน class_schedules / class_slots (จองห้อง หน้า /admin/scheduler).

Revision ID: 20261024_02
Revises: 20261024_01
Create Date: 2026-10-24

DDL เหมือนที่ create_all สร้างจาก app/models/booking_request.py, class_schedule.py, class_slot.py
IF NOT EXISTS ทุกตัว รันซ้ำได้
"""

from alembic import op


revision = "20261024_02"
down_revision = "20261024_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        "ALTER TABLE class_schedules ADD COLUMN IF NOT EXISTS room varchar(64)",
        "ALTER TABLE class_slots ADD COLUMN IF NOT EXISTS room varchar(64)",
        """DO $$ BEGIN
               ALTER TABLE class_slots ADD CONSTRAINT ex_class_slots_room_overlap
                   EXCLUDE USING gist (room WITH =, tstzrange(starts_at, ends_at) WITH &&)
                   WHERE (room IS NOT NULL AND deleted_at IS NULL AND status <> 'CANCELLED');
           EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
           END $$""",
        """CREATE TABLE IF NOT EXISTS booking_requests (
            id uuid PRIMARY KEY,
            requested_by uuid NOT NULL REFERENCES users(id),
            course_id uuid NOT NULL REFERENCES courses(id),
            lab_id uuid NOT NULL REFERENCES labs(id),
            weekday integer NOT NULL,
            start_time time without time zone NOT NULL,
            end_time time without time zone NOT NULL,
            valid_from date NOT NULL,
            valid_until date NOT NULL,
            machines integer NOT NULL,
            room varchar(64),
            note text,
            status varchar(16) DEFAULT 'pending' NOT NULL,
            decided_by uuid REFERENCES users(id),
            decided_at timestamp with time zone,
            decision_note text,
            class_schedule_id uuid REFERENCES class_schedules(id),
            mail_status varchar(16),
            mail_error text,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT ck_booking_requests_weekday CHECK (weekday BETWEEN 0 AND 6),
            CONSTRAINT ck_booking_requests_time_order CHECK (end_time > start_time),
            CONSTRAINT ck_booking_requests_date_order CHECK (valid_until >= valid_from),
            CONSTRAINT ck_booking_requests_machines CHECK (machines > 0),
            CONSTRAINT ck_booking_requests_status CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled'))
        )""",
        "CREATE INDEX IF NOT EXISTS ix_booking_requests_requested_by ON booking_requests (requested_by)",
        "CREATE INDEX IF NOT EXISTS ix_booking_requests_status ON booking_requests (status)",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS booking_requests")
    op.execute("ALTER TABLE class_slots DROP CONSTRAINT IF EXISTS ex_class_slots_room_overlap")
    op.execute("ALTER TABLE class_slots DROP COLUMN IF EXISTS room")
    op.execute("ALTER TABLE class_schedules DROP COLUMN IF EXISTS room")
