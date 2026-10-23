"""Add class_schedules, class_slots and sessions.class_slot_id.

Statements are idempotent so databases where create_all() already created
class_schedules/class_slots can still be upgraded (only sessions.class_slot_id
was missing there).

Revision ID: 20261023_01
Revises: 20261018_01
Create Date: 2026-10-23
"""

from alembic import op


revision = "20261023_01"
down_revision = "20261018_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        # Needed for the exclusion constraint (uuid WITH = in a gist index)
        "CREATE EXTENSION IF NOT EXISTS btree_gist",
        """DO $$ BEGIN
            CREATE TYPE classslotstatus AS ENUM
                ('SCHEDULED', 'PREWARMING', 'READY', 'DONE', 'CANCELLED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$""",
        """CREATE TABLE IF NOT EXISTS class_schedules (
            id UUID NOT NULL PRIMARY KEY,
            course_id UUID NOT NULL REFERENCES courses (id),
            weekday INTEGER NOT NULL,
            start_time TIME WITHOUT TIME ZONE NOT NULL,
            end_time TIME WITHOUT TIME ZONE NOT NULL,
            valid_from DATE NOT NULL,
            valid_until DATE NOT NULL,
            default_lab_image_id UUID REFERENCES lab_images (id),
            expected_seats INTEGER NOT NULL,
            created_by UUID NOT NULL REFERENCES users (id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT ck_class_schedules_weekday CHECK (weekday BETWEEN 0 AND 6),
            CONSTRAINT ck_class_schedules_time_order CHECK (end_time > start_time),
            CONSTRAINT ck_class_schedules_date_order CHECK (valid_until >= valid_from),
            CONSTRAINT ck_class_schedules_seats CHECK (expected_seats > 0)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_class_schedules_course_id ON class_schedules (course_id)",
        "CREATE INDEX IF NOT EXISTS ix_class_schedules_id ON class_schedules (id)",
        "CREATE INDEX IF NOT EXISTS ix_class_schedules_deleted_at ON class_schedules (deleted_at)",
        """CREATE TABLE IF NOT EXISTS class_slots (
            id UUID NOT NULL PRIMARY KEY,
            schedule_id UUID REFERENCES class_schedules (id),
            course_id UUID NOT NULL REFERENCES courses (id),
            lab_id UUID REFERENCES labs (id),
            lab_image_id UUID NOT NULL REFERENCES lab_images (id) ON DELETE RESTRICT,
            starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
            ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
            expected_seats INTEGER NOT NULL,
            run_target runtarget DEFAULT 'KUBERNETES' NOT NULL,
            status classslotstatus DEFAULT 'SCHEDULED' NOT NULL,
            note TEXT,
            created_by UUID NOT NULL REFERENCES users (id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT ck_class_slots_time_order CHECK (ends_at > starts_at),
            CONSTRAINT ck_class_slots_seats CHECK (expected_seats > 0),
            CONSTRAINT ex_class_slots_no_overlap EXCLUDE USING gist (
                course_id WITH =, tstzrange(starts_at, ends_at) WITH &&
            ) WHERE (deleted_at IS NULL AND status <> 'CANCELLED')
        )""",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_id ON class_slots (id)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_starts_at ON class_slots (starts_at)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_schedule_id ON class_slots (schedule_id)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_deleted_at ON class_slots (deleted_at)",
        "CREATE INDEX IF NOT EXISTS ix_class_slots_course_starts_at ON class_slots (course_id, starts_at)",
        # The column that was missing
        """ALTER TABLE sessions
           ADD COLUMN IF NOT EXISTS class_slot_id UUID
           REFERENCES class_slots (id) ON DELETE SET NULL""",
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
