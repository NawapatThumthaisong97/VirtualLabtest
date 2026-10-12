from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from decimal import Decimal, ROUND_UP
import os
import re
import sky
import yaml

from app.models.session import Session as SessionModel, SessionStatus, ServiceType
from app.models.user import User
from app.models.enrollment import Enrollment, RoleInCourse
from app.models.lab import Lab, LabStatus
from app.models.lab_image import ImageStatus, LabImage
from app.repositories.session_repository import SessionRepository
from app.repositories.lab_repository import LabRepository
from app.repositories.lab_image_repository import LabImageRepository
from app.exceptions.domain import (
    SessionNotFoundError,
    UserNotFoundError,
    LabNotFoundError,
    LabImageNotFoundError,
    LabImageMissingError,
    SessionAlreadyExistsError,
    ClusterOperationError,
    ForbiddenError,
)
from app.services.quota_reservation_service import QuotaReservationService


class SessionService:
    """Service สำหรับ business logic ของ Session"""

    def __init__(
        self,
        db: Session,
        session_repository: SessionRepository,
        lab_repository: LabRepository,
        lab_image_repository: LabImageRepository,
        quota_reservation_service: QuotaReservationService | None = None,
    ):
        self.db = db
        self.session_repository = session_repository
        self.lab_repository = lab_repository
        self.lab_image_repository = lab_image_repository
        self.quota_reservation_service = quota_reservation_service or QuotaReservationService(db)

    def get_all_sessions(
        self, user_id: Optional[UUID] = None, status: Optional[SessionStatus] = None
    ) -> list[SessionModel]:
        """ดึง sessions ทั้งหมด"""
        return self.session_repository.get_all(user_id=user_id, status=status)

    def get_session_by_id(self, session_id: UUID) -> SessionModel:
        """ดึง session ตาม ID"""
        session = self.session_repository.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session with id {session_id} not found")
        return session


    def create_fastapi_task(
        self,
        lab_image: LabImage,
        app_name: str,
        env: str = "production",
    ) -> str:
        """สร้าง SkyPilot task YAML จาก LabImage model"""
        docker_registry_host = os.getenv("DOCKER_REGISTRY_HOST", "100.127.74.48:5001")
        full_image = f"{docker_registry_host}/{lab_image.full_image_name}"
        image_id = f"docker:{full_image}"
        
        resources = lab_image.get_skypilot_resources()
        
        ports_list = resources.get("ports", [])
        if ports_list:
            ports_yaml = "\n".join([f"    - {port}" for port in ports_list])
            ports_section = f"\n  ports:\n{ports_yaml}"
        else:
            ports_section = ""
        
    
        env_vars = lab_image.env_vars or {}
        env_vars["APP_ENV"] = env 
        if env_vars:
            env_yaml = "\n".join([f"  {key}: {value}" for key, value in env_vars.items()])
            envs_section = f"\nenvs:\n{env_yaml}\n"
        else:
            envs_section = ""
        
   
        idle_minutes = lab_image.lifespan_minutes or 60
        
        # Optional
        workdir_section = ""
        if lab_image.workdir:
            workdir_section = f"\nworkdir: {lab_image.workdir}\n"

        yaml_str = f"""name: {app_name}

resources:
  infra: kubernetes
  cpus: {resources['cpus']}
  memory: {resources['memory']}
  disk_size: {resources.get('disk_size', 50)}
  image_id: {image_id}{ports_section}
  autostop:
    idle_minutes: {idle_minutes}
    down: true
    wait_for: none
{workdir_section}{envs_section}
run: |
  {lab_image.entrypoint_script or '/bin/bash /run.sh'}
"""
        return yaml_str

    def create_session(self, user_id: UUID, lab_id: UUID) -> dict:
        """สร้าง session ใหม่ - launch pod และบันทึกลง database"""
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(f"User with id {user_id} not found")
        
        lab = self.lab_repository.find_by_id(lab_id)
        if not lab or lab.deleted_at is not None or lab.status != LabStatus.PUBLISHED:
            raise LabNotFoundError(f"Lab with id {lab_id} not found")

        enrollment = (
            self.db.query(Enrollment.user_id)
            .filter(
                Enrollment.user_id == user_id,
                Enrollment.course_id == lab.course_id,
                Enrollment.role_in_course == RoleInCourse.STUDENT,
            )
            .first()
        )
        if enrollment is None:
            raise ForbiddenError("ต้องลงทะเบียนในวิชานี้ก่อนเริ่ม lab")
        
        existing_session = (
            self.db.query(SessionModel)
            .filter(
                SessionModel.user_id == user_id,
                SessionModel.lab_id == lab_id,
                SessionModel.status == SessionStatus.RUNNING,
                SessionModel.deleted_at.is_(None)
            )
            .first()
        )
        
     
        if existing_session and existing_session.sky_cluster_name:
        
            try:
                request_id = sky.status(cluster_names=[existing_session.sky_cluster_name])
                cluster_records = sky.get(request_id)
                
                if not cluster_records:
    
                    existing_session.status = SessionStatus.STOPPED
                    existing_session.ended_at = datetime.utcnow()
                    self.db.commit()
        
                    existing_session = None
                else:
                
                    cluster_status = cluster_records[0].get('status')
                    from sky import ClusterStatus
                    
                    if cluster_status == ClusterStatus.STOPPED:
                        # Cluster หยุดแล้ว → อัพเดท status เป็น STOPPED
                        existing_session.status = SessionStatus.STOPPED
                        existing_session.ended_at = datetime.utcnow()
                        self.db.commit()
                        
                        existing_session = None
                
            except Exception as e:
                raise ClusterOperationError(
                    "Could not verify the existing cluster state; refusing to start a duplicate"
                ) from e
        
        if existing_session:
            raise SessionAlreadyExistsError(
                f"User already has a running session for this lab. Session ID: {existing_session.id}, Cluster: {existing_session.sky_cluster_name}"
            )
        
        if not lab.image_id:
            raise LabImageMissingError(f"Lab {lab_id} does not have an image assigned")
        
        lab_image = self.lab_image_repository.find_by_id(lab.image_id)
        if (
            not lab_image
            or lab_image.status != ImageStatus.APPROVED
            or lab_image.course_id != lab.course_id
        ):
            raise LabImageNotFoundError(f"LabImage with id {lab.image_id} not found")
        
        cluster_name = f"music-lab-{uuid4().hex[:12]}"
       
        

        task_yaml = self.create_fastapi_task(
            lab_image=lab_image,
            app_name=cluster_name,
            env="staging",
        )

        task = sky.Task.from_yaml_config(yaml.safe_load(task_yaml))
        compute_hours, storage_mb = self._quota_requirements(lab_image)
        reservation_ids = self.quota_reservation_service.reserve_personal_cluster(
            user_id, compute_hours, storage_mb
        )
        is_cluster_launch_attempted = False
        try:
            is_cluster_launch_attempted = True
            request_id = sky.launch(task, cluster_name=cluster_name)
            job_id, _ = sky.stream_and_get(request_id)
            endpoints = sky.get(sky.endpoints(cluster=cluster_name))

            formatted_endpoints = {
                str(port): f"http://{url}" if not url.startswith("http") else url
                for port, url in endpoints.items()
            }

            new_session = SessionModel(
                user_id=user_id,
                lab_id=lab_id,
                lab_image_id=lab_image.id,
                service_type=ServiceType.LAB,
                sky_cluster_name=cluster_name,
                sky_job_id=job_id,
                endpoints=formatted_endpoints,
                status=SessionStatus.RUNNING,
                started_at=datetime.utcnow(),
                is_remote=False,
                is_cloud=False,
            )

            self.db.add(new_session)
            self.quota_reservation_service.mark_committed(reservation_ids)
            self.db.commit()
            self.db.refresh(new_session)
        except Exception as error:
            self.db.rollback()
            if is_cluster_launch_attempted:
                try:
                    sky.down(cluster_name)
                except Exception as cleanup_error:
                    raise ClusterOperationError(
                        "Cluster provisioning failed and cleanup could not be verified; quota remains reserved"
                    ) from cleanup_error
            self.quota_reservation_service.release(reservation_ids)
            if isinstance(error, ClusterOperationError):
                raise
            raise ClusterOperationError("Cluster provisioning failed") from error

        return {
            "session_id": new_session.id,
            "cluster_name": cluster_name,
            "lab_id": lab_id,
            "lab_title": lab.title,
            "image_repository": lab_image.repository,
            "image_tag": lab_image.tag,
            "endpoints": formatted_endpoints,
            "status": "running",
            "started_at": new_session.started_at,
        }

    @staticmethod
    def _quota_requirements(lab_image: LabImage) -> tuple[Decimal, int]:
        cpu_match = re.match(r"\s*(\d+(?:\.\d+)?)", lab_image.cpu_requirement)
        if cpu_match is None:
            raise LabImageMissingError("Lab image has an invalid CPU requirement")

        cpu_count = Decimal(cpu_match.group(1))
        lifespan_hours = Decimal(lab_image.lifespan_minutes or 60) / Decimal(60)
        compute_hours = (cpu_count * lifespan_hours).quantize(
            Decimal("0.01"), rounding=ROUND_UP
        )
        storage_mb = max(int(lab_image.disk_size or 0) * 1024, 1)
        return compute_hours, storage_mb

    def delete_session(self, session_id: UUID) -> dict:
        """ลบ session - stop cluster (ถ้ายังรัน) และ soft delete"""
        
        session = self.session_repository.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session with id {session_id} not found")
        
        is_cluster_stopped = False
        if session.status == SessionStatus.RUNNING:
            # RUNNING แต่ไม่มี sky_cluster_name = record ค้าง ไม่ใช่ cluster ที่รันอยู่จริง
            # เกิดได้จาก seed, จาก create ที่พังกลางทางก่อนบันทึกชื่อ cluster, หรือ
            # จากการแก้ DB ตรง ๆ
            #
            # เดิมโยน error ทิ้งตรงนี้ ทำให้ลบไม่ได้เลย แต่ create_session ก็ยังนับว่า
            # ผู้ใช้มี session RUNNING อยู่แล้วเลยตอบ 409 กลับมา ติดตายทั้งสองทาง
            # ทางเดียวที่ออกได้คือไปแก้ DB เอง ซึ่งไม่ควรเป็นคำตอบของ API
            #
            # ไม่มี cluster ก็แค่ไม่มีอะไรให้ปิด ปล่อยให้ไปลบต่อได้ตามปกติ
            if session.sky_cluster_name:
                try:
                    sky.down(session.sky_cluster_name)
                    is_cluster_stopped = True
                except Exception as e:
                    raise ClusterOperationError(
                        f"Failed to stop cluster {session.sky_cluster_name}: {str(e)}"
                    )

            session.status = SessionStatus.STOPPED
            session.ended_at = datetime.utcnow()
            self.db.commit()

        self.session_repository.soft_delete(session)
        
        return {
            "session_id": session_id,
            "cluster_name": session.sky_cluster_name,
            "isClusterStopped": is_cluster_stopped,
            "message": "Session deleted successfully" if not is_cluster_stopped
                      else "Session stopped and deleted successfully"
        }