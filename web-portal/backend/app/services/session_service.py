from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
import io
import os
import re
import shlex
import sky
import time
from sky.exceptions import ClusterDoesNotExist

from app.adapters.ecr_adapter import get_ecr_token
from app.configs.settings import settings
from app.services.kubernetes_service import get_kubernetes_service
from app.services.warm_pod_service import (DIRECT_POD_PREFIX, LAB_LABEL, WARM_POD_PREFIX, WarmPodService,
                                           build_lab_pod, direct_pod_name, is_ready, pod_problem,
                                           warm_endpoints)

from app.models.session import Session as SessionModel, SessionStatus, SessionEndReason, ServiceType
from app.models.class_slot import ClassSlot, ClassSlotStatus
from app.services import admin_billing_service
from app.models.user import User
from app.models.lab import Lab, LabStatus, RunTarget
from app.models.lab_image import ImageStatus, LabImage
from app.models.enrollment import Enrollment, RoleInCourse
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
    CloudBurstDisabledError,
)
from app.utils.logger import logger

# session ที่ PENDING นานกว่านี้ถือว่าค้าง (launch จริง: K3s ~5 นาที, AWS ~2.5 นาที)
PENDING_TIMEOUT = timedelta(minutes=20)

# รอ job ของ lab ผ่าน setup จนเป็น RUNNING (AWS: docker login + pull ~10 วินาที)
JOB_START_TIMEOUT = timedelta(minutes=10)
JOB_POLL_SECONDS = 5
JOB_STARTING_STATUSES = {None, "INIT", "PENDING", "SETTING_UP"}

# ตอน launch พัง เก็บท้าย log ของ job ไว้ก่อนลบ cluster (ลบแล้ว sky logs ดูไม่ได้อีก)
FAILED_LOG_TAIL_LINES = 50

# pod ตรง / รอ warm pod: เช็กสถานะ pod ทุกกี่วินาที
POD_POLL_SECONDS = 2


def get_warm_pod_service() -> WarmPodService:
    # แยกเป็นฟังก์ชันให้เทสแทนด้วย FakeK8s ได้
    return WarmPodService(get_kubernetes_service())


def resolve_run_target(client_node: Optional[tuple[str, str]]) -> RunTarget:
    """กฎเดียวทุก lab (docs/LAB_DIRECT_POD.md): กดจากเครื่องแลป → KUBERNETES, ที่อื่น / เช็กไม่ได้ → AWS

    client_node = ผลของ _client_node (None = ไม่ใช่เครื่องแลป หรือเช็กไม่ได้) ไม่ดู labs.run_target แล้ว
    """
    return RunTarget.KUBERNETES if client_node is not None else RunTarget.AWS


def _is_pod_session(session) -> bool:
    """session ที่ได้ pod ของเราเอง (warm pod / pod ตรง) ไม่มี cluster ของ SkyPilot — ลบ / ดูแลด้วย k8s API

    แยกจาก seed ที่มี k8s_pod_name แต่ไม่มี pod จริง ด้วย prefix ของชื่อ pod
    """
    return not session.sky_cluster_name and (session.k8s_pod_name or "").startswith(
        (WARM_POD_PREFIX, DIRECT_POD_PREFIX))


class SessionService:
    """Service สำหรับ business logic ของ Session"""

    def __init__(
        self,
        db: Session,
        session_repository: SessionRepository,
        lab_repository: LabRepository,
        lab_image_repository: LabImageRepository,
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
        pin_node: Optional[str] = None,
    ) -> dict:
        """สร้าง SkyPilot task config (dict) จาก LabImage ตาม run_target ของ lab

        pin_node = ชื่อ node ที่ต้องให้ pod ลง (K3s เท่านั้น ดู LAB_ISOLATION_ENABLED)

        คืนเป็น dict แล้วส่งเข้า sky.Task.from_yaml_config ตรง ๆ แทนการต่อ YAML ด้วย
        f-string แบบเดิม ซึ่งพังเมื่อค่า env มี ':' หรือ '#' และเมื่อ entrypoint มีหลายบรรทัด
        """
        if run_target == RunTarget.AWS:
            return self._build_aws_task(lab_image, app_name, env)
        return self._build_k8s_task(lab_image, app_name, env, pin_node)

    def _lab_envs(self, lab_image: LabImage, env: str) -> dict[str, str]:
        envs = {k: str(v) for k, v in (lab_image.env_vars or {}).items()}
        envs["APP_ENV"] = env
        return envs

    def _autostop(self, lab_image: LabImage) -> dict:
        # wait_for: none = ลบ cluster เมื่อครบ idle_minutes โดยไม่รอ job หรือ SSH
        # lifespan_minutes จึงเป็นอายุสูงสุดของ lab ไม่ใช่เวลานับหลังเลิกใช้
        return {
            "idle_minutes": lab_image.lifespan_minutes or 60,
            "down": True,
            "wait_for": "none",
        }

    def _build_k8s_task(self, lab_image: LabImage, app_name: str, env: str,
                        pin_node: Optional[str] = None) -> dict:
        """K3s on-prem: SkyPilot รัน image เป็น pod ตรง ๆ (container mode)

        pin_node: บังคับ pod ลงเครื่องที่กด Start และติด label vlab/lab ให้ NetworkPolicy
        vlab-lab-isolation ปิดขาเข้าจากเครื่องอื่น (kubernetes.pod_config เป็น override ที่ task ตั้งได้)
        """
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
        if pin_node:
            task["config"] = {"kubernetes": {"pod_config": {
                "metadata": {"labels": {LAB_LABEL: "true"}},
                "spec": {"nodeSelector": {"kubernetes.io/hostname": pin_node}},
            }}}
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
        # entrypoint ว่าง = ใช้ ENTRYPOINT/CMD ของ image เอง เช่น code-server ที่ตั้ง ENTRYPOINT ไว้
        # ถ้าต่อคำสั่งท้าย docker run จะกลายเป็น argument ของ ENTRYPOINT นั้นแล้วพัง
        # (K3s ใช้ไม่ได้แบบนี้ เพราะ SkyPilot แทน command ของ pod เอง ต้องมี run เสมอ)
        entrypoint = (lab_image.entrypoint_script or "").strip()
        command = f" /bin/bash -c {shlex.quote(entrypoint)}" if entrypoint else ""

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
            # foreground: job อยู่ใน RUNNING ตลอดที่ lab เปิด (_wait_job_running ใช้สถานะนี้)
            # ส่ง entrypoint เป็นก้อนเดียวผ่าน bash -c ถ้าต่อท้ายตรง ๆ แล้ว entrypoint มีหลายบรรทัด
            # บรรทัดที่ 2 เป็นต้นไปจะไปรันบน VM แทนที่จะรันใน container
            "run": f"{docker_run} {shlex.quote(image)}{command}\n",
        }

    def _cluster_name(self, lab_image: LabImage) -> str:
        # ชื่อ cluster ของ SkyPilot ต้องเป็นตัวเล็ก ตัวเลข และ '-' ขึ้นต้นด้วยตัวอักษร
        slug = re.sub(r"[^a-z0-9-]+", "-", lab_image.repository.split("/")[-1].lower()).strip("-")
        if not slug[:1].isalpha():
            # เช่น repo "2048-game" SkyPilot ไม่รับชื่อที่ขึ้นต้นด้วยตัวเลข
            slug = f"lab-{slug}".rstrip("-")
        return f"{slug}-{int(time.time())}"

    def create_session(self, user_id: UUID, lab_id: UUID, client_ip: Optional[str] = None) -> dict:
        """สร้าง session ใหม่ - launch pod และบันทึกลง database

        client_ip = IP ของเครื่องที่ส่ง request มา ใช้หา warm pod บนเครื่องที่นักศึกษานั่งอยู่
        """
        
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
                # PENDING ด้วย กันกด Start ซ้ำระหว่างที่ launch รอบแรกยังไม่เสร็จ
                SessionModel.status.in_([SessionStatus.RUNNING, SessionStatus.PENDING]),
                SessionModel.deleted_at.is_(None)
            )
            .first()
        )

        # PENDING = launch รอบก่อนยังไม่จบ ห้ามไปถาม sky.status เพราะช่วงไม่กี่วินาทีแรก
        # SkyPilot ยังไม่มี record ของ cluster โค้ดข้างล่างจะเข้าใจว่า cluster หายแล้ว
        # ตั้ง STOPPED แล้วปล่อย launch ซ้อน (เทสกับ K3s จริงได้ 2 pod ของ user เดียวกัน)
        if existing_session and existing_session.status == SessionStatus.PENDING:
            if not self._is_stale_pending(existing_session):
                raise SessionAlreadyExistsError(
                    f"Session is still starting. Session ID: {existing_session.id}, Cluster: {existing_session.sky_cluster_name}"
                )
            # ค้างเกิน timeout = backend ตายกลาง launch ไม่มีใครมาอัปเดต record นี้แล้ว
            self._end_session(existing_session, SessionStatus.FAILED, SessionEndReason.STALE_PENDING)
            self._cleanup_quietly(existing_session)
            existing_session = None

        if existing_session and _is_pod_session(existing_session):
            # warm pod ไม่มี sky.status ให้ถาม ดู pod เอง หายแล้ว = ปิด session เดิมแล้วเปิดใหม่ได้
            try:
                if not get_warm_pod_service().pod_exists(existing_session.k8s_pod_name):
                    self._end_session(existing_session, SessionStatus.STOPPED,
                                      self._gone_reason(existing_session))
                    existing_session = None
            except Exception as e:
                # ต่อ K3s ไม่ได้ ไม่รู้ว่า pod ยังอยู่ไหม ถือว่ายังอยู่ (ตอบ 409) ดีกว่าเปิดซ้อน
                logger.warning(f"[warm pod] cannot check {existing_session.k8s_pod_name}: {e}")

        if existing_session and existing_session.sky_cluster_name:

            try:
                request_id = sky.status(cluster_names=[existing_session.sky_cluster_name])
                cluster_records = sky.get(request_id)

                if not cluster_records:

                    self._end_session(existing_session, SessionStatus.STOPPED,
                                      self._gone_reason(existing_session))

                    existing_session = None
                else:

                    cluster_status = cluster_records[0].get('status')
                    from sky import ClusterStatus

                    if cluster_status in [ClusterStatus.STOPPED, ClusterStatus.AUTOSTOPPING]:
                        # Cluster หยุดแล้ว → อัพเดท status เป็น STOPPED
                        self._end_session(existing_session, SessionStatus.STOPPED,
                                          self._gone_reason(existing_session))

                        existing_session = None

            except Exception as e:
                # ถาม SkyPilot ไม่ได้ (เช่น "Could not connect to SkyPilot API server") = ไม่รู้ว่า cluster
                # เดิมยังอยู่ไหม เดิมเดาว่าหยุดแล้ว ตั้ง STOPPED แล้ว launch ต่อ → cluster เดิมไม่ถูก down
                # (ลบ session ทีหลังก็ข้ามเพราะเห็นว่า STOPPED) ค้างกินเครื่องจน autostop และเปิดซ้อนได้
                # ไม่แตะ session เดิม ให้กดใหม่ทีหลัง เหมือน warm pod ที่ต่อ K3s ไม่ได้
                logger.warning(f"[session] cannot check cluster {existing_session.sky_cluster_name}: {e}")
                raise ClusterOperationError(
                    f"Cannot verify existing session {existing_session.id} "
                    f"(cluster {existing_session.sky_cluster_name}), please try again: {e}"
                )
        
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
        
        # กฎเดียวทุก lab: เครื่องแลป → K8s (warm pod / pod ตรง), ที่อื่น → EC2 (docs/LAB_DIRECT_POD.md)
        # ต้องรู้เสมอว่ากดจากเครื่องแลปไหม ไม่ขึ้นกับ WARM_POD / LAB_ISOLATION
        node = self._client_node(client_ip, always=True)
        run_target = resolve_run_target(node)
        where = f"lab machine {node[0]}" if node else f"outside ({client_ip or 'unknown ip'})"
        logger.info(f"[auto] Start from {where} -> {run_target.value}")
        if node is not None:
            # นั่งอยู่ที่เครื่องแลปที่มี warm pod ว่าง → ใช้เลย ไม่ต้องรอ
            warm = self._try_warm_pod(user_id, lab, lab_image, node)
            if warm is None and self._wait_starting_warm_pod(node[0], lab_image):
                warm = self._try_warm_pod(user_id, lab, lab_image, node)
            if warm is not None:
                return warm
            if settings.LAB_MACHINE_LAUNCH == "pod":
                return self._launch_direct_pod(user_id, lab, lab_image, node)
            # LAB_MACHINE_LAUNCH=skypilot: ทางเดิม SkyPilot in-cluster pin เครื่องนั้น (ข้างล่าง)

        if run_target == RunTarget.AWS and not admin_billing_service.is_burst_enabled(self.db):
            raise CloudBurstDisabledError(
                "ปิดการเปิด lab บน AWS ชั่วคราว (admin ปิด burst เช่นใช้เกิน budget) — ใช้เครื่องในห้องแลปแทน"
            )

        cluster_name = self._cluster_name(lab_image)
        is_cloud = run_target == RunTarget.AWS
        pin_node = node[0] if node is not None and settings.LAB_ISOLATION_ENABLED else None

        task_config = self.create_fastapi_task(
            lab_image=lab_image,
            app_name=cluster_name,
            env="staging",
            run_target=run_target,
            pin_node=pin_node,
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

            class_slot_id=self._current_slot_id(lab),
        )
        self.db.add(new_session)
        self.db.commit()
        self.db.refresh(new_session)

        job_id = None
        try:
            request_id = sky.launch(task, cluster_name=cluster_name)
            job_id, handle = sky.stream_and_get(request_id)
            self._wait_job_running(cluster_name, job_id)
            endpoints = sky.get(sky.endpoints(cluster=cluster_name))
        except Exception as e:
            self._end_session(new_session, SessionStatus.FAILED, SessionEndReason.LAUNCH_FAILED)
            if job_id is not None:
                logger.warning(
                    f"[launch failed] {cluster_name} job {job_id} log tail:\n"
                    f"{self._job_log_tail(cluster_name, job_id)}"
                )
            self._down_quietly(cluster_name)
            raise ClusterOperationError(f"Failed to launch cluster {cluster_name}: {e}")

        formatted_endpoints = {
            str(port): f"http://{url}" if not url.startswith("http") else url
            for port, url in endpoints.items()
        }

        new_session.sky_job_id = job_id
        new_session.endpoints = formatted_endpoints
        new_session.status = SessionStatus.RUNNING
        # autostop เริ่มนับตอน launch เสร็จ (wait_for: none) หน้าเว็บใช้นับถอยหลังได้
        new_session.expires_at = datetime.utcnow() + timedelta(
            minutes=lab_image.lifespan_minutes or 60
        )
        self.db.commit()
        self.db.refresh(new_session)

        return {
            "session_id": new_session.id,
            "cluster_name": cluster_name,
            "launch_mode": "skypilot",
            "run_target": run_target.value,
            "lab_id": lab_id,
            "lab_title": lab.title,
            "image_repository": lab_image.repository,
            "image_tag": lab_image.tag,
            "endpoints": formatted_endpoints,
            "status": "running",
            "started_at": new_session.started_at,
            "expires_at": new_session.expires_at,
        }

    def _current_slot_id(self, lab: Lab) -> Optional[UUID]:
        """คาบของวิชานี้ที่กำลังเรียนอยู่ตอนนี้ (หน้า admin ใช้บอกว่าห้องไหนใช้โดยคาบอะไร) ไม่มี = None

        วิชาเดียวกันเวลาทับกันไม่ได้ (ex_class_slots_no_overlap) จึงมีอย่างมากคาบเดียว
        """
        now = datetime.now(timezone.utc)
        slot = (
            self.db.query(ClassSlot.id)
            .filter(
                ClassSlot.course_id == lab.course_id,
                ClassSlot.starts_at <= now,
                ClassSlot.ends_at > now,
                ClassSlot.status != ClassSlotStatus.CANCELLED,
                ClassSlot.deleted_at.is_(None),
            )
            .first()
        )
        return slot.id if slot else None

    def _client_node(self, client_ip: Optional[str], always: bool = False) -> Optional[tuple[str, str]]:
        """(ชื่อ node, IP) ถ้า IP ของ request ตรงกับ InternalIP ของ worker ที่ Ready (= นั่งเครื่องนั้นจริง)

        หาเฉพาะตอนเปิด WARM_POD_ENABLED หรือ LAB_ISOLATION_ENABLED (always = หาเสมอ ใช้กับ lab AUTO)
        ต่อ K3s ไม่ได้ = None (launch ต่อได้ — lab AUTO จึงไป AWS แทน)
        """
        if not client_ip:
            return None
        if not always and not (settings.WARM_POD_ENABLED or settings.LAB_ISOLATION_ENABLED):
            return None
        try:
            return get_warm_pod_service().node_for_ip(client_ip)
        except Exception as e:
            logger.warning(f"[lab node] cannot look up node for {client_ip}: {e}")
            return None

    def _try_warm_pod(self, user_id: UUID, lab: Lab, lab_image: LabImage,
                      node: tuple[str, str]) -> Optional[dict]:
        """แจก warm pod บนเครื่องที่กด Start คืน None ถ้าใช้ไม่ได้ (ให้ไป SkyPilot ต่อ)

        เงื่อนไขทั้งหมดต้องจริง:
        1. เปิด WARM_POD_ENABLED
        2. IP ของ request ตรงกับ InternalIP ของ worker ที่ Ready (_client_node หาให้แล้ว)
        3. เครื่องนั้นมี warm pod ของ lab image นี้ที่ว่าง และ Running + Ready
        4. แย่ง pod สำเร็จ (ไม่มีคนอื่นได้ไปก่อน)
        K3s ต่อไม่ได้หรือพังตรงไหนก็ไป SkyPilot แทน ไม่ให้นักศึกษาเปิด lab ไม่ได้เพราะ warm pod
        """
        if not settings.WARM_POD_ENABLED:
            return None
        node_name, node_ip = node
        try:
            warm = get_warm_pod_service()
            pod = warm.find_free_pod(node_name, lab_image.id)
            if pod is None:
                logger.info(f"[warm pod] no free pod for {lab_image.full_image_name} on {node_name}")
                return None
            session_id = uuid4()
            if not warm.claim(pod, session_id):
                logger.info(f"[warm pod] {pod.metadata.name} was claimed by someone else")
                return None
        except Exception as e:
            logger.warning(f"[warm pod] lookup failed, falling back to SkyPilot: {e}")
            return None

        now = datetime.utcnow()
        session = SessionModel(
            id=session_id,
            user_id=user_id,
            lab_id=lab.id,
            lab_image_id=lab_image.id,
            service_type=ServiceType.LAB,
            k8s_pod_name=pod.metadata.name,
            node_name=node_name,
            endpoints=warm_endpoints(node_ip, lab_image),
            status=SessionStatus.RUNNING,
            started_at=now,
            # ไม่มี autostop ของ SkyPilot reconciler ลบ pod เองเมื่อถึงเวลานี้
            expires_at=now + timedelta(minutes=lab_image.lifespan_minutes or 60),
            is_remote=False,
            is_cloud=False,
            class_slot_id=self._current_slot_id(lab),
        )
        try:
            self.db.add(session)
            self.db.commit()
        except Exception:
            self.db.rollback()
            # pod ถูก claim ไปแล้วแต่ไม่มี session ชี้ ลบทิ้งให้ DaemonSet สร้างตัวใหม่ ไม่งั้นค้างตลอด
            warm.delete_pod(pod.metadata.name)
            raise
        self.db.refresh(session)
        logger.info(f"[warm pod] {pod.metadata.name} on {node_name} -> session {session.id}")

        return {
            "session_id": session.id,
            "cluster_name": None,
            "launch_mode": "warm_pod",
            "run_target": RunTarget.KUBERNETES.value,
            "node_name": node_name,
            "lab_id": lab.id,
            "lab_title": lab.title,
            "image_repository": lab_image.repository,
            "image_tag": lab_image.tag,
            "endpoints": session.endpoints,
            "status": "running",
            "started_at": session.started_at,
            "expires_at": session.expires_at,
        }

    def _wait_starting_warm_pod(self, node_name: str, lab_image: LabImage) -> bool:
        """warm pod ของ image นี้บนเครื่องนี้กำลังขึ้น (DaemonSet เพิ่งสร้างแทนตัวที่คนก่อนปิด) → รอจน Ready

        คืน True ถ้ารอแล้วมีตัวพร้อม (ให้ _try_warm_pod อีกรอบ) ไม่รอ = สร้าง pod ตรงชนกับ warm pod ที่จองที่ไว้
        → เครื่องเต็ม (เทสหน้าเว็บ 2026-10-21 กด Start ซ้ำทันทีหลังปิด)
        """
        if not settings.WARM_POD_ENABLED or settings.WARM_POD_WAIT_SECONDS <= 0:
            return False
        try:
            warm = get_warm_pod_service()
            if not warm.has_starting_pod(node_name, lab_image.id):
                return False
            logger.info(f"[warm pod] waiting for starting pod on {node_name}")
            deadline = time.monotonic() + settings.WARM_POD_WAIT_SECONDS
            while time.monotonic() < deadline:
                time.sleep(POD_POLL_SECONDS)
                if warm.find_free_pod(node_name, lab_image.id) is not None:
                    return True
                if not warm.has_starting_pod(node_name, lab_image.id):
                    return False
        except Exception as e:
            logger.warning(f"[warm pod] wait failed: {e}")
        return False

    def _launch_direct_pod(self, user_id: UUID, lab: Lab, lab_image: LabImage,
                           node: tuple[str, str]) -> dict:
        """pod ตรงบนเครื่องที่กด Start (ไม่มี warm pod) — ไม่ผ่าน SkyPilot (docs/LAB_DIRECT_POD.md)

        บันทึก PENDING ก่อนสร้าง pod: backend ตายกลางทาง reconciler ยังตามลบ pod ได้ (STALE_PENDING)
        เครื่องไม่มีที่ว่าง → error บอกตรง ๆ ไม่ส่งไป EC2 (เครื่องแลปเป็นของ lab อย่างเดียว)
        """
        node_name, node_ip = node
        session_id = uuid4()
        pod_name = direct_pod_name(session_id)
        session = SessionModel(
            id=session_id,
            user_id=user_id,
            lab_id=lab.id,
            lab_image_id=lab_image.id,
            service_type=ServiceType.LAB,
            k8s_pod_name=pod_name,
            node_name=node_name,
            status=SessionStatus.PENDING,
            started_at=datetime.utcnow(),
            is_remote=False,
            is_cloud=False,
            class_slot_id=self._current_slot_id(lab),
        )
        self.db.add(session)
        self.db.commit()

        warm = get_warm_pod_service()
        try:
            warm.create_pod(build_lab_pod(lab_image, node_name, session_id))
            problem = None
            deadline = time.monotonic() + settings.DIRECT_POD_READY_TIMEOUT
            while True:
                pod = warm.read_pod(pod_name)
                if is_ready(pod):
                    break
                problem = pod_problem(pod)
                if problem is not None or time.monotonic() >= deadline:
                    break
                time.sleep(POD_POLL_SECONDS)
        except Exception as e:
            problem = f"{type(e).__name__}: {e}"

        if problem is not None or not is_ready(pod):
            problem = problem or f"not ready after {settings.DIRECT_POD_READY_TIMEOUT}s"
            # ลบแล้ว log หาย — เก็บท้าย log ไว้ก่อน (EC2 ใช้ _job_log_tail เหมือนกัน)
            logger.warning(f"[pod failed] {pod_name} on {node_name}: {problem}\n{warm.pod_log_tail(pod_name)}")
            self._end_session(session, SessionStatus.FAILED, SessionEndReason.LAUNCH_FAILED)
            self._cleanup_quietly(session)
            if problem.startswith("Unschedulable"):
                raise ClusterOperationError(
                    f"เครื่อง {node_name} ไม่มีที่ว่างสำหรับ lab นี้ ({problem})")
            raise ClusterOperationError(f"Failed to start lab pod {pod_name}: {problem}")

        session.endpoints = warm_endpoints(node_ip, lab_image)
        session.status = SessionStatus.RUNNING
        # ไม่มี autostop ของ SkyPilot reconciler ลบ pod เองเมื่อถึงเวลานี้ (เหมือน warm pod)
        session.expires_at = datetime.utcnow() + timedelta(minutes=lab_image.lifespan_minutes or 60)
        self.db.commit()
        self.db.refresh(session)
        logger.info(f"[pod] {pod_name} on {node_name} -> session {session.id}")

        return {
            "session_id": session.id,
            "cluster_name": None,
            "launch_mode": "pod",
            "run_target": RunTarget.KUBERNETES.value,
            "node_name": node_name,
            "lab_id": lab.id,
            "lab_title": lab.title,
            "image_repository": lab_image.repository,
            "image_tag": lab_image.tag,
            "endpoints": session.endpoints,
            "status": "running",
            "started_at": session.started_at,
            "expires_at": session.expires_at,
        }

    def _cleanup_quietly(self, session: SessionModel) -> None:
        """ลบเครื่องของ session ที่พัง / ค้าง: cluster ของ SkyPilot หรือ pod ของเรา ลบไม่ได้แค่ log"""
        if session.sky_cluster_name:
            self._down_quietly(session.sky_cluster_name)
        elif _is_pod_session(session):
            try:
                get_warm_pod_service().delete_pod(session.k8s_pod_name)
            except Exception as e:
                logger.warning(f"Failed to clean up pod {session.k8s_pod_name}: {e}")

    def _wait_job_running(self, cluster_name: str, job_id: int) -> None:
        """sky.launch คืนตั้งแต่ส่ง job ส่วน setup ไปรันต่อเองทีหลัง ถ้าไม่รอ setup ที่พัง
        (เช่น docker pull tag ที่ไม่มี) จะถูกบันทึกเป็น RUNNING ทั้งที่ job เป็น FAILED_SETUP
        และเครื่องค้างอยู่ (เทสกับ AWS จริงแล้ว) raise แล้ว create_session จะลบ cluster ให้เอง
        """
        deadline = time.monotonic() + JOB_START_TIMEOUT.total_seconds()
        while True:
            status = sky.get(sky.job_status(cluster_name, [job_id])).get(job_id)
            status = getattr(status, "value", status)
            if status == "RUNNING":
                return
            if status not in JOB_STARTING_STATUSES:
                raise ClusterOperationError(f"Lab job {job_id} did not start: {status}")
            if time.monotonic() > deadline:
                raise ClusterOperationError(f"Lab job {job_id} still {status} after {JOB_START_TIMEOUT}")
            time.sleep(JOB_POLL_SECONDS)

    def _is_stale_pending(self, session: SessionModel) -> bool:
        if not session.started_at:
            return True
        started_at = session.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - started_at > PENDING_TIMEOUT

    def _end_session(
        self,
        session: SessionModel,
        status: SessionStatus,
        reason: Optional[SessionEndReason],
    ) -> None:
        session.status = status
        session.ended_at = datetime.utcnow()
        session.end_reason = reason
        # ชั่วโมงที่ใช้ + ค่า AWS ประมาณ (หน้า admin billing) commit พร้อมสถานะ
        admin_billing_service.record_usage(self.db, session)
        self.db.commit()

    def _gone_reason(self, session: SessionModel) -> SessionEndReason:
        """cluster หายหลัง expires_at = autostop ตามเวลา ก่อนหน้านั้น = เครื่อง/pod ตายเอง"""
        expires_at = session.expires_at
        if expires_at is None:
            return SessionEndReason.LOST
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            return SessionEndReason.EXPIRED
        return SessionEndReason.LOST

    def _job_log_tail(self, cluster_name: str, job_id: int) -> str:
        buf = io.StringIO()
        try:
            sky.tail_logs(cluster_name, job_id, follow=False,
                          tail=FAILED_LOG_TAIL_LINES, output_stream=buf)
        except Exception as e:
            return f"(cannot fetch job log: {e})"
        # ตัดรหัสสีของ terminal ที่ SkyPilot ใส่มา ไม่งั้นอ่านใน log file ลำบาก
        return re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())

    def _down_quietly(self, cluster_name: str) -> None:
        """ลบ cluster ที่ launch พัง ถ้าลบไม่ได้ก็แค่ log ไว้ ไม่ทับ error ของ launch"""
        try:
            sky.get(sky.down(cluster_name))
        except ClusterDoesNotExist:
            pass
        except Exception as e:
            logger.warning(f"Failed to clean up cluster {cluster_name}: {e}")

    def reconcile_sessions(self) -> dict:
        """ปิด session ที่เครื่องหายไปแล้วแต่ DB ยังไม่รู้ (autostop, pod/EC2 ตายเอง) และ
        PENDING ที่ค้างเกิน timeout ให้ session_reconciler เรียกเป็นระยะ

        เรียก sky.status ครั้งเดียวต่อรอบ ถ้าเรียกไม่ได้ (API server ล่ม) จะไม่แตะ session
        RUNNING เลย เพราะไม่รู้จริงว่าเครื่องยังอยู่ไหม
        """
        active = (
            self.db.query(SessionModel)
            .filter(
                SessionModel.status.in_([SessionStatus.RUNNING, SessionStatus.PENDING]),
                SessionModel.deleted_at.is_(None),
            )
            .all()
        )
        result = {"checked": len(active), "stopped": [], "failed": []}

        for session in active:
            if session.status == SessionStatus.PENDING and self._is_stale_pending(session):
                self._end_session(session, SessionStatus.FAILED, SessionEndReason.STALE_PENDING)
                self._cleanup_quietly(session)
                result["failed"].append(session.sky_cluster_name or session.k8s_pod_name)

        warm = [s for s in active if s.status == SessionStatus.RUNNING and _is_pod_session(s)]
        if warm:
            self._reconcile_warm(warm, result)

        # ไม่มีชื่อ cluster = record ที่ไม่ได้มาจาก launch จริง (เช่น seed) ไม่ใช่งานของ reconciler
        running = [
            s for s in active
            if s.status == SessionStatus.RUNNING and s.sky_cluster_name
        ]
        if not running:
            return result

        # AUTO = refresh เฉพาะ cluster ที่ตั้ง autostop ไว้ ซึ่ง lab ทุกตัวตั้ง ไม่ refresh
        # แล้ว API server จะยังเห็นเครื่องที่ skylet ลบตัวเองไปแล้วเป็น UP อยู่
        records = sky.get(sky.status(
            cluster_names=[s.sky_cluster_name for s in running],
            refresh=sky.StatusRefreshMode.AUTO,
        ))
        alive = {r.get("name"): r.get("status") for r in records}
        for session in running:
            # AUTOSTOPPING ยังไม่นับว่าหาย เคยเห็นค้างสถานะนี้ตอน autostop ลบเครื่องไม่สำเร็จ
            if alive.get(session.sky_cluster_name) in (None, sky.ClusterStatus.STOPPED):
                self._end_session(session, SessionStatus.STOPPED, self._gone_reason(session))
                result["stopped"].append(session.sky_cluster_name)
        return result

    def _reconcile_warm(self, sessions: list[SessionModel], result: dict) -> None:
        """session ของ warm pod: ไม่มี autostop ของ SkyPilot ต้องลบ pod เองเมื่อถึง expires_at
        และปิด session ที่ pod หายไปเอง (เครื่องดับ / มีคนลบ)

        ต่อ K3s ไม่ได้ = ไม่แตะ session เลยรอบนี้ (เหมือนตอน SkyPilot ล่ม)
        """
        try:
            warm = get_warm_pod_service()
        except Exception as e:
            logger.warning(f"[warm pod] reconcile skipped, K3s unavailable: {e}")
            return
        now = datetime.now(timezone.utc)
        for session in sessions:
            try:
                expires_at = session.expires_at
                if expires_at is not None and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at is not None and now >= expires_at:
                    warm.delete_pod(session.k8s_pod_name)
                    self._end_session(session, SessionStatus.STOPPED, SessionEndReason.EXPIRED)
                    result["stopped"].append(session.k8s_pod_name)
                elif not warm.pod_exists(session.k8s_pod_name):
                    self._end_session(session, SessionStatus.STOPPED, SessionEndReason.LOST)
                    result["stopped"].append(session.k8s_pod_name)
            except Exception as e:
                logger.warning(f"[warm pod] reconcile {session.k8s_pod_name} failed: {e}")

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
            if _is_pod_session(session):
                # ลบ pod แล้ว DaemonSet จะสร้างตัวใหม่ที่สะอาดให้คนถัดไปที่นั่งเครื่องนี้
                try:
                    get_warm_pod_service().delete_pod(session.k8s_pod_name)
                    cluster_stopped = True
                except Exception as e:
                    raise ClusterOperationError(
                        f"Failed to delete warm pod {session.k8s_pod_name}: {str(e)}"
                    )
            elif session.sky_cluster_name:
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

            self._end_session(session, SessionStatus.STOPPED, SessionEndReason.USER_DELETE)

        self.session_repository.soft_delete(session)
        
        return {
            "session_id": session_id,
            "cluster_name": session.sky_cluster_name,
            "cluster_stopped": cluster_stopped,
        }