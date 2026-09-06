from uuid import UUID
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Any
import os
import sky
import yaml
import time

from app.models.session import Session as SessionModel, SessionStatus, ServiceType
from app.models.user import User
from app.models.lab import Lab
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
    InvalidSessionStateError,
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
        if not lab:
            raise LabNotFoundError(f"Lab with id {lab_id} not found")
        
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
        
        cluster_name = f"music-lab-{int(time.time())}"
       
        

        task_yaml = self.create_fastapi_task(
            lab_image=lab_image,
            app_name=cluster_name,
            env="staging",
        )

        task = sky.Task.from_yaml_config(yaml.safe_load(task_yaml))

        request_id = sky.launch(
            task,
            cluster_name=cluster_name,
        )

        job_id, handle = sky.stream_and_get(request_id)
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

    def delete_session(self, session_id: UUID) -> dict:
        """ลบ session - stop cluster (ถ้ายังรัน) และ soft delete"""
        
        session = self.session_repository.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError(f"Session with id {session_id} not found")
        
        cluster_stopped = False
        if session.status == SessionStatus.RUNNING:
            if not session.sky_cluster_name:
                raise InvalidSessionStateError("Session does not have a cluster name")
            
            try:
                sky.down(session.sky_cluster_name)
                cluster_stopped = True
                
                session.status = SessionStatus.STOPPED
                session.ended_at = datetime.utcnow()
                self.db.commit()
                
            except Exception as e:
                raise ClusterOperationError(
                    f"Failed to stop cluster {session.sky_cluster_name}: {str(e)}"
                )
        
        self.session_repository.soft_delete(session)
        
        return {
            "session_id": session_id,
            "cluster_name": session.sky_cluster_name,
            "cluster_stopped": cluster_stopped,
            "message": "Session deleted successfully" if not cluster_stopped 
                      else "Session stopped and deleted successfully"
        }