from uuid import UUID
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Any
import os
import re
import shlex
import sky
import time
from sky.exceptions import ClusterDoesNotExist

from app.adapters.ecr_adapter import get_ecr_token
from app.configs.settings import settings

from app.models.session import Session as SessionModel, SessionStatus, ServiceType
from app.models.user import User
from app.models.lab import Lab, RunTarget
from app.models.lab_image import LabImage
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
)


class SessionService:
    """Service สำหรับ business logic ของ Session"""

    def __init__(
        self,
        db: Session,
        session_repository: SessionRepository,
        lab_repository: LabRepository,
        lab_image_repository: LabImageRepository
    ):
        self.db = db
        self.session_repository = session_repository
        self.lab_repository = lab_repository
        self.lab_image_repository = lab_image_repository

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
        run_target: RunTarget = RunTarget.KUBERNETES,
    ) -> dict:
        """สร้าง SkyPilot task config (dict) จาก LabImage ตาม run_target ของ lab

        คืนเป็น dict แล้วส่งเข้า sky.Task.from_yaml_config ตรง ๆ แทนการต่อ YAML ด้วย
        f-string แบบเดิม ซึ่งพังเมื่อค่า env มี ':' หรือ '#' และเมื่อ entrypoint มีหลายบรรทัด
        """
        if run_target == RunTarget.AWS:
            return self._build_aws_task(lab_image, app_name, env)
        return self._build_k8s_task(lab_image, app_name, env)

    def _lab_envs(self, lab_image: LabImage, env: str) -> dict[str, str]:
        envs = {k: str(v) for k, v in (lab_image.env_vars or {}).items()}
        envs["APP_ENV"] = env
        return envs

    def _autostop(self, lab_image: LabImage) -> dict:
        return {
            "idle_minutes": lab_image.lifespan_minutes or 60,
            "down": True,
            "wait_for": "none",
        }

    def _build_k8s_task(self, lab_image: LabImage, app_name: str, env: str) -> dict:
        """K3s on-prem: SkyPilot รัน image เป็น pod ตรง ๆ (container mode)"""
        docker_registry_host = os.getenv("DOCKER_REGISTRY_HOST", "100.127.74.48:5001")
        resources_req = lab_image.get_skypilot_resources()

        resources: dict[str, Any] = {
            "infra": "kubernetes",
            "cpus": resources_req["cpus"],
            "memory": resources_req["memory"],
            "disk_size": resources_req.get("disk_size", 50),
            "image_id": f"docker:{docker_registry_host}/{lab_image.full_image_name}",
            "autostop": self._autostop(lab_image),
        }
        if resources_req.get("ports"):
            resources["ports"] = resources_req["ports"]

        task: dict[str, Any] = {
            "name": app_name,
            "resources": resources,
            "envs": self._lab_envs(lab_image, env),
            "run": lab_image.entrypoint_script or "/bin/bash /run.sh",
        }
        if lab_image.workdir:
            task["workdir"] = lab_image.workdir
        return task

    def _build_aws_task(self, lab_image: LabImage, app_name: str, env: str) -> dict:
        """AWS: VM mode บน EC2 ใน private subnet

        ไม่ใช้ image_id: docker: เพราะแบบนั้น SkyPilot ต้องลง runtime ลงใน container ใหม่
        ทุกครั้ง (~5 นาที) และ image ของ lab ไม่ได้ตั้ง HOME ไว้ ใช้ AMI ที่ bake runtime
        ไว้แล้ว แล้ว docker run image จาก ECR เองแทน (~1 นาที)

        ECR_TOKEN ไม่ได้ใส่ตรงนี้ create_session ส่งเข้าเป็น secret ตอน launch
        """
        if not settings.ECR_REGISTRY_HOST or not settings.AWS_LAB_AMI:
            raise ClusterOperationError(
                "AWS launch is not configured: set ECR_REGISTRY_HOST and AWS_LAB_AMI"
            )

        image = f"{settings.ECR_REGISTRY_HOST}/{lab_image.full_image_name}"
        ports = lab_image.get_skypilot_resources().get("ports") or []

        # env ของ lab ต้องส่งเข้า container ไม่ใช่ VM เลยแปลงเป็น -e ของ docker run
        docker_args = ["--rm", "--name", "lab"]
        docker_args += [arg for port in ports for arg in ("-p", f"{port}:{port}")]
        for key, value in self._lab_envs(lab_image, env).items():
            docker_args += ["-e", f"{key}={value}"]
        if lab_image.workdir:
            docker_args += ["-w", lab_image.workdir]
        docker_run = "sudo docker run " + " ".join(shlex.quote(a) for a in docker_args)
        entrypoint = lab_image.entrypoint_script or "/bin/bash /run.sh"

        resources: dict[str, Any] = {
            "infra": f"aws/{settings.AWS_REGION}",
            "instance_type": settings.AWS_INSTANCE_TYPE,
            "disk_size": settings.AWS_DISK_SIZE,
            "image_id": settings.AWS_LAB_AMI,
            "autostop": self._autostop(lab_image),
        }
        if ports:
            resources["ports"] = ports

        registry = shlex.quote(settings.ECR_REGISTRY_HOST)
        return {
            "name": app_name,
            "resources": resources,
            "setup": (
                f'echo "$ECR_TOKEN" | sudo docker login -u AWS --password-stdin {registry}\n'
                f"sudo docker pull {shlex.quote(image)}\n"
            ),
            # foreground: SkyPilot ถือว่า job ยังรันอยู่ autostop จะนับ idle หลัง lab ปิดเท่านั้น
            "run": f"{docker_run} {shlex.quote(image)} {entrypoint}\n",
        }

    def _cluster_name(self, lab_image: LabImage) -> str:
        # ชื่อ cluster ของ SkyPilot ต้องเป็นตัวเล็ก ตัวเลข และ '-' ขึ้นต้นด้วยตัวอักษร
        slug = re.sub(r"[^a-z0-9-]+", "-", lab_image.repository.split("/")[-1].lower()).strip("-")
        return f"{slug or 'lab'}-{int(time.time())}"

    def create_session(self, user_id: UUID, lab_id: UUID) -> dict:
        """สร้าง session ใหม่ - launch pod และบันทึกลง database"""
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError(f"User with id {user_id} not found")
        
        lab = self.lab_repository.find_by_id(lab_id)
        if not lab:
            raise LabNotFoundError(f"Lab with id {lab_id} not found")
        
        existing_session = (
            self.db.query(SessionModel)
            .filter(
                SessionModel.user_id == user_id,
                SessionModel.lab_id == lab_id,
                # PENDING ด้วย กันกด Start ซ้ำระหว่างที่ launch รอบแรกยังไม่เสร็จ
                SessionModel.status.in_([SessionStatus.RUNNING, SessionStatus.PENDING]),
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
                    
                    if cluster_status in [ClusterStatus.STOPPED, ClusterStatus.AUTOSTOPPING]:
                        # Cluster หยุดแล้ว → อัพเดท status เป็น STOPPED
                        existing_session.status = SessionStatus.STOPPED
                        existing_session.ended_at = datetime.utcnow()
                        self.db.commit()
                        
                        existing_session = None
                
            except Exception as e:
                
                print(f"[Warning] Failed to check cluster status: {e}")
                existing_session.status = SessionStatus.STOPPED
                existing_session.ended_at = datetime.utcnow()
                self.db.commit()
                existing_session = None
        
        if existing_session:
            raise SessionAlreadyExistsError(
                f"User already has a running session for this lab. Session ID: {existing_session.id}, Cluster: {existing_session.sky_cluster_name}"
            )
        
        if not lab.image_id:
            raise LabImageMissingError(f"Lab {lab_id} does not have an image assigned")
        
        lab_image = self.lab_image_repository.find_by_id(lab.image_id)
        if not lab_image:
            raise LabImageNotFoundError(f"LabImage with id {lab.image_id} not found")
        
        cluster_name = self._cluster_name(lab_image)
        run_target = lab.run_target or RunTarget.KUBERNETES
        is_cloud = run_target == RunTarget.AWS

        task_config = self.create_fastapi_task(
            lab_image=lab_image,
            app_name=cluster_name,
            env="staging",
            run_target=run_target,
        )
        # ขอ token ก่อนสร้าง record จะได้ไม่มี session ค้างถ้าแค่ขอ token ไม่ผ่าน
        secrets = None
        if run_target == RunTarget.AWS:
            try:
                secrets = [("ECR_TOKEN", get_ecr_token(settings.AWS_REGION))]
            except Exception as e:
                raise ClusterOperationError(f"Failed to get ECR token: {e}")
        task = sky.Task.from_yaml_config(task_config, secrets_overrides=secrets)

        # บันทึกเป็น PENDING ก่อน launch ถ้า launch พังกลางทางจะยังรู้ชื่อ cluster ไว้ตามลบ
        # (บน AWS cluster ที่ไม่มี record คือ EC2 ที่เปิดค้างเสียเงินโดยไม่มีใครเห็น)
        new_session = SessionModel(
            user_id=user_id,
            lab_id=lab_id,
            lab_image_id=lab_image.id,
            service_type=ServiceType.LAB,
            sky_cluster_name=cluster_name,
            status=SessionStatus.PENDING,
            started_at=datetime.utcnow(),
            is_remote=False,
            is_cloud=is_cloud,
        )
        self.db.add(new_session)
        self.db.commit()
        self.db.refresh(new_session)

        try:
            request_id = sky.launch(task, cluster_name=cluster_name)
            job_id, handle = sky.stream_and_get(request_id)
            endpoints = sky.get(sky.endpoints(cluster=cluster_name))
        except Exception as e:
            new_session.status = SessionStatus.FAILED
            new_session.ended_at = datetime.utcnow()
            self.db.commit()
            self._down_quietly(cluster_name)
            raise ClusterOperationError(f"Failed to launch cluster {cluster_name}: {e}")

        formatted_endpoints = {
            str(port): f"http://{url}" if not url.startswith("http") else url
            for port, url in endpoints.items()
        }

        new_session.sky_job_id = job_id
        new_session.endpoints = formatted_endpoints
        new_session.status = SessionStatus.RUNNING
        self.db.commit()
        self.db.refresh(new_session)

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

    def _down_quietly(self, cluster_name: str) -> None:
        """ลบ cluster ที่ launch พัง ถ้าลบไม่ได้ก็แค่ log ไว้ ไม่ทับ error ของ launch"""
        try:
            sky.get(sky.down(cluster_name))
        except ClusterDoesNotExist:
            pass
        except Exception as e:
            print(f"[Warning] Failed to clean up cluster {cluster_name}: {e}")

    def delete_session(self, session_id: UUID) -> dict:
        """ลบ session - stop cluster (ถ้ายังรัน) และ soft delete"""
        
        session = self.session_repository.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session with id {session_id} not found")
        
        cluster_stopped = False
        if session.status in (SessionStatus.RUNNING, SessionStatus.PENDING):
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
                    # sky.down คืน request_id ต้อง sky.get ถึงจะรู้ว่าลบเสร็จหรือพังจริง
                    sky.get(sky.down(session.sky_cluster_name))
                    cluster_stopped = True
                except ClusterDoesNotExist:
                    # autostop ลบไปเองแล้ว ไม่มีอะไรให้ปิด
                    pass
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
            "cluster_stopped": cluster_stopped,
            "message": "Session deleted successfully" if not cluster_stopped 
                      else "Session stopped and deleted successfully"
        }