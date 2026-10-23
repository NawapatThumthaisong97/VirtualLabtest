"""
POST /api/lab-image — ขอ presigned URL อัปโหลด docker image (.tar) ขึ้น R2
"""
import re
import uuid
from datetime import datetime, timezone

import pytest

from app.models.lab_image import ImageStatus, LabImage
from app.services.lab_image_service import build_archive_key

ENDPOINT = "/api/lab-image"
MIB = 1024 * 1024


def _row(db, image_id) -> LabImage:
    db.expire_all()
    return db.get(LabImage, uuid.UUID(image_id))


def _key_pattern(course_code: str, image_id: str) -> re.Pattern:
    """lab-images/{code}_{yyyy}_{mm}_{dd}_{image_id 8 ตัวแรก}_image.tar"""
    short = uuid.UUID(image_id).hex[:8]
    return re.compile(rf"^lab-images/{re.escape(course_code)}_\d{{4}}_\d{{2}}_\d{{2}}_{short}_image\.tar$")


class TestPresignAuthorization:
    """Presign authorization"""

    def test_no_token_is_401(self, client, upload_body):
        """Request without a token is rejected with 401"""
        assert client.post(ENDPOINT, json=upload_body()).status_code == 401

    def test_student_is_403(self, client, world, auth, upload_body):
        """A student cannot request an upload URL"""
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.student))
        assert response.status_code == 403

    def test_instructor_of_other_course_is_403(self, client, world, auth, upload_body, db):
        """An instructor who does not teach the course gets 403 and no row is created"""
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.outsider))
        assert response.status_code == 403
        assert db.query(LabImage).count() == 0

    def test_owner_is_201(self, client, world, auth, upload_body):
        """The instructor who created the course can upload"""
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.owner))
        assert response.status_code == 201

    def test_enrolled_co_instructor_is_201(self, client, world, auth, upload_body):
        """An instructor enrolled as INSTRUCTOR in the course can upload"""
        response = client.post(
            ENDPOINT, json=upload_body(), headers=auth(world.co_instructor)
        )
        assert response.status_code == 201

    def test_admin_can_upload_to_any_course(self, client, world, auth, upload_body):
        """Admin has global access to every course"""
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.admin))
        assert response.status_code == 201

    def test_unknown_course_is_404(self, client, world, auth, upload_body):
        """A course that does not exist returns 404"""
        response = client.post(
            ENDPOINT,
            json=upload_body(courseId=str(uuid.uuid4())),
            headers=auth(world.owner),
        )
        assert response.status_code == 404

    def test_soft_deleted_course_is_404(self, client, world, auth, upload_body):
        """A soft-deleted course returns 404 even for its creator"""
        response = client.post(
            ENDPOINT,
            json=upload_body(courseId=str(world.deleted_course.id)),
            headers=auth(world.owner),
        )
        assert response.status_code == 404


class TestPresignResult:
    """Presign result"""

    def test_response_and_archive_key(self, client, world, auth, upload_body, fake_r2):
        """Response carries a server-built archive key and a PUT URL signed for application/x-tar"""
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.owner))
        assert response.status_code == 201
        data = response.json()["data"]

        expected_key = data["archiveKey"]
        assert _key_pattern(world.course.code, data["imageId"]).match(expected_key)
        assert data["method"] == "PUT"
        assert data["headers"] == {"Content-Type": "application/x-tar"}
        assert data["status"] == "pending"
        assert expected_key in data["uploadUrl"]
        assert data["expiresAt"]
        assert fake_r2.presigned == [
            {"key": expected_key, "content_type": "application/x-tar", "expires_in": 900}
        ]

    def test_draft_row_saved(self, client, db, world, auth, upload_body):
        """The draft row stores request metadata, uploader from JWT and empty archive fields"""
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.owner))
        image = _row(db, response.json()["data"]["imageId"])

        assert image.status is ImageStatus.PENDING
        assert image.uploaded_by == world.owner.id
        assert image.course_id == world.course.id
        assert (image.repository, image.tag) == ("skypilot/music-lab-test", "lab-01")
        assert image.image_digest is None
        assert image.size_mb == 2048
        assert image.exposed_ports == [8080, 5173, 8443]
        assert image.entrypoint_script == "/bin/bash /run.sh"
        assert image.workdir == "/workspace"
        assert image.env_vars == {"IDE_PASSWORD": "musiclab"}
        assert image.archive_key.endswith("_image.tar")
        assert image.archive_etag is None
        assert image.archive_size_bytes is None
        assert image.archive_uploaded_at is None

    def test_size_mb_rounds_up(self, client, db, world, auth, upload_body):
        """Declared size is rounded up to whole MiB"""
        response = client.post(
            ENDPOINT, json=upload_body(fileSizeBytes=MIB + 1), headers=auth(world.owner)
        )
        assert _row(db, response.json()["data"]["imageId"]).size_mb == 2

    def test_defaults_when_only_required_fields(self, client, db, world, auth):
        """Optional fields fall back to the model defaults"""
        response = client.post(
            ENDPOINT,
            json={
                "courseId": str(world.course.id),
                "repository": "vlab/min",
                "tag": "v1",
                "fileSizeBytes": 1024,
            },
            headers=auth(world.owner),
        )
        assert response.status_code == 201
        image = _row(db, response.json()["data"]["imageId"])
        assert image.cpu_requirement == "2+"
        assert image.memory_requirement == "4+"
        assert image.disk_size == 50
        assert image.lifespan_minutes == 60
        assert image.exposed_ports == []
        assert image.entrypoint_script == "/bin/bash /run.sh"
        assert image.workdir is None
        assert image.env_vars is None

    def test_server_owned_fields_are_ignored(self, client, db, world, auth, upload_body):
        """Client cannot choose archive key, status, digest or uploader"""
        response = client.post(
            ENDPOINT,
            json=upload_body(
                archiveKey="../../evil.tar",
                status="approved",
                imageDigest="sha256:fake",
                uploadedBy=str(world.admin.id),
            ),
            headers=auth(world.owner),
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert _key_pattern(world.course.code, data["imageId"]).match(data["archiveKey"])
        image = _row(db, data["imageId"])
        assert image.status is ImageStatus.PENDING
        assert image.image_digest is None
        assert image.uploaded_by == world.owner.id


class TestArchiveKey:
    """Archive key format"""

    IMAGE_ID = uuid.UUID("6b67aa30-d170-492f-9524-1555a5b7a0ca")

    def test_format(self):
        """Key is lab-images/{course code}_{yyyy}_{mm}_{dd}_{short image id}_image.tar"""
        now = datetime(2026, 10, 23, 5, 0, tzinfo=timezone.utc)
        assert build_archive_key("SE301", self.IMAGE_ID, now) == (
            "lab-images/SE301_2026_10_23_6b67aa30_image.tar"
        )

    def test_date_uses_thai_time(self):
        """18:00 UTC is already the next day in Bangkok, and the key follows Bangkok time"""
        now = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
        assert "_2026_10_24_" in build_archive_key("SE301", self.IMAGE_ID, now)

    @pytest.mark.parametrize(
        "code, expected",
        [
            ("SE 301", "SE-301"),
            ("../../etc", "etc"),
            ("SE/301*x", "SE-301-x"),
            ("วิชา", "course"),
            ("", "course"),
        ],
    )
    def test_course_code_is_sanitized(self, code, expected):
        """Regression: characters outside A-Z a-z 0-9 - never reach the key (no slash or dot-dot)"""
        now = datetime(2026, 10, 23, 5, 0, tzinfo=timezone.utc)
        key = build_archive_key(code, self.IMAGE_ID, now)
        assert key == f"lab-images/{expected}_2026_10_23_6b67aa30_image.tar"
        assert key.count("/") == 1 and ".." not in key

    def test_two_images_same_course_same_day_get_different_keys(self, create_draft):
        """Regression: images of one course uploaded on the same day must not share a key (R2 PUT would overwrite)"""
        first = create_draft(tag="lab-01")
        second = create_draft(tag="lab-02")
        assert first["archiveKey"] != second["archiveKey"]

    def test_short_id_collision_is_retried(self, monkeypatch, create_draft):
        """If the 8-char id suffix collides with an existing key, a new image id is drawn"""
        ids = iter(
            [
                uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001"),  # first image
                uuid.UUID("aaaaaaaa-0000-4000-8000-000000000002"),  # same first 8 chars -> same key
                uuid.UUID("bbbbbbbb-0000-4000-8000-000000000003"),  # retry succeeds
            ]
        )
        monkeypatch.setattr("app.services.lab_image_service.uuid.uuid4", lambda: next(ids))
        first = create_draft(tag="lab-01")
        second = create_draft(tag="lab-02")
        assert first["archiveKey"].endswith("_aaaaaaaa_image.tar")
        assert second["archiveKey"].endswith("_bbbbbbbb_image.tar")
        assert second["imageId"] == "bbbbbbbb-0000-4000-8000-000000000003"

    def test_key_survives_course_rename(self, client, db, world, auth, upload_body, create_draft):
        """A draft keeps its key when the course code changes later, so the webhook still matches"""
        first = create_draft()
        world.course.code = "RENAMED1"
        db.commit()
        second = client.post(ENDPOINT, json=upload_body(), headers=auth(world.owner)).json()["data"]
        assert second["archiveKey"] == first["archiveKey"]


class TestPresignValidation:
    """Presign request validation"""

    @pytest.mark.parametrize(
        "overrides",
        [
            {"courseId": "not-a-uuid"},
            {"repository": "../Evil"},
            {"repository": "UPPER/case"},
            {"repository": ""},
            {"tag": "-bad"},
            {"tag": "has space"},
            {"fileSizeBytes": 0},
            {"fileSizeBytes": 6 * 1024**3},
            {"exposedPorts": [8080, 8080]},
            {"exposedPorts": [0]},
            {"exposedPorts": [70000]},
            {"diskSize": 0},
            {"lifespanMinutes": -1},
            {"envVars": {"A": 1}},
        ],
        ids=lambda o: next(iter(o)) + "=" + str(next(iter(o.values())))[:12],
    )
    def test_invalid_body_is_400(self, client, world, auth, upload_body, overrides, db):
        """Regression: custom validator errors return 400, not a 500 from the JSON handler"""
        response = client.post(
            ENDPOINT, json=upload_body(**overrides), headers=auth(world.owner)
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "validation_error"
        assert db.query(LabImage).count() == 0

    def test_missing_course_id_is_400(self, client, world, auth, upload_body):
        """courseId is required in the body"""
        body = upload_body()
        del body["courseId"]
        response = client.post(ENDPOINT, json=body, headers=auth(world.owner))
        assert response.status_code == 400

    def test_empty_body_is_400(self, client, world, auth):
        """An empty JSON object is rejected"""
        response = client.post(ENDPOINT, json={}, headers=auth(world.owner))
        assert response.status_code == 400


class TestPresignDuplicates:
    """Duplicate repository:tag handling"""

    def test_same_owner_reuses_draft(self, client, db, world, auth, upload_body, fake_r2):
        """Requesting again for an un-uploaded draft reuses the row and key, refreshing metadata"""
        first = client.post(ENDPOINT, json=upload_body(), headers=auth(world.owner)).json()["data"]
        second = client.post(
            ENDPOINT, json=upload_body(diskSize=70), headers=auth(world.owner)
        )
        assert second.status_code == 201
        data = second.json()["data"]

        assert data["imageId"] == first["imageId"]
        assert data["archiveKey"] == first["archiveKey"]
        assert db.query(LabImage).count() == 1
        assert _row(db, data["imageId"]).disk_size == 70
        assert len(fake_r2.presigned) == 2

    def test_other_instructors_draft_is_409(self, client, world, auth, upload_body, create_draft):
        """A draft belonging to another instructor cannot be taken over"""
        create_draft()
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.co_instructor))
        assert response.status_code == 409

    def test_uploaded_image_is_409(self, client, world, auth, upload_body, db, create_draft):
        """Once the archive is on R2 the same repository:tag cannot be requested again"""
        from datetime import datetime, timezone

        draft = create_draft()
        _row(db, draft["imageId"]).archive_uploaded_at = datetime.now(timezone.utc)
        db.commit()
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.owner))
        assert response.status_code == 409

    def test_approved_image_is_409(self, client, world, auth, upload_body, db, create_draft):
        """An approved image cannot be replaced through this endpoint"""
        draft = create_draft()
        _row(db, draft["imageId"]).status = ImageStatus.APPROVED
        db.commit()
        response = client.post(ENDPOINT, json=upload_body(), headers=auth(world.owner))
        assert response.status_code == 409

    def test_same_tag_in_other_course_is_409(self, client, db, world, auth, upload_body, create_draft):
        """repository:tag is unique across courses, so another course cannot reuse it"""
        from app.models.courses import Course

        create_draft()
        other = Course(
            code=f"T{uuid.uuid4().hex[:6]}",
            name="Other",
            lecturer_name="X",
            created_by=world.owner.id,
        )
        db.add(other)
        db.commit()
        response = client.post(
            ENDPOINT, json=upload_body(courseId=str(other.id)), headers=auth(world.owner)
        )
        assert response.status_code == 409


class TestPresignWithoutR2Config:
    """Presign when R2 is not configured"""

    def test_no_draft_left_behind(self, db, world, monkeypatch):
        """Regression: missing R2 settings raise before any draft row is committed"""
        from app.adapters.r2_adapter import R2Adapter, R2NotConfiguredError
        from app.configs.settings import settings
        from app.repositories.lab_image_repository import LabImageRepository
        from app.schemas.lab_image_schema import LabImageUploadRequest
        from app.services.lab_image_service import LabImageService

        for name in ("R2_ACCOUNT_ID", "R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID",
                     "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
            monkeypatch.setattr(settings, name, None)

        service = LabImageService(db, LabImageRepository(db), R2Adapter())
        payload = LabImageUploadRequest(
            course_id=world.course.id, repository="vlab/x", tag="v1", file_size_bytes=1024
        )
        with pytest.raises(R2NotConfiguredError):
            service.create_upload(payload, world.owner)
        db.rollback()
        assert db.query(LabImage).count() == 0
