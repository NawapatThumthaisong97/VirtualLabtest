"""
services/skypilot_service.py
─────────────────────────────────────────────────────────────────────────────
SkyPilot SDK wrapper — AI Learner Lab Control Plane

CONSTRAINT #2: All calls are async (non-blocking). SkyPilot's blocking SDK
               calls are run in a thread pool via asyncio.to_thread() so they
               never block the FastAPI event loop.

CONSTRAINT #3: Job type determines which YAML task definition is loaded:
               - "normal" → sky_tasks/ml_job.yaml  (K3s first, AWS fallback)
               - "burst"  → sky_tasks/burst_test.yaml  (force AWS Spot only)
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import logging
import os
from pathlib import Path

import sky  # SkyPilot SDK

logger = logging.getLogger(__name__)

# Path to YAML task definitions (relative to this file's package root)
_TASK_DIR = Path(__file__).parent.parent / "sky_tasks"

# Map job_type → task YAML file
_TASK_YAML_MAP: dict[str, Path] = {
    "normal": _TASK_DIR / "ml_job.yaml",
    "burst": _TASK_DIR / "burst_test.yaml",
}


def _build_task(job_id: str, job_type: str, config: dict) -> sky.Task:
    """
    Load the appropriate SkyPilot Task from YAML and inject runtime env vars.

    Args:
        job_id:   UUID of the job (from PostgreSQL record).
        job_type: "normal" or "burst".
        config:   Additional config dict from the API request payload.

    Returns:
        A configured sky.Task ready for sky.launch().
    """
    yaml_path = _TASK_YAML_MAP.get(job_type)
    if yaml_path is None:
        raise ValueError(
            f"Unknown job_type '{job_type}'. "
            f"Valid types: {list(_TASK_YAML_MAP.keys())}"
        )
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"SkyPilot task YAML not found: {yaml_path}. "
            "Ensure sky_tasks/ directory is present in the container."
        )

    task = sky.Task.from_yaml(str(yaml_path))

    # Inject runtime environment variables into the task
    task.update_envs({
        "JOB_ID": job_id,
        "S3_BUCKET": os.getenv("S3_BUCKET", "virtuallab-ml-artifacts"),
        **{k: str(v) for k, v in config.items()},  # pass extra config as env vars
    })

    return task


async def launch_job(job_id: str, job_type: str, config: dict) -> str:
    """
    Launch a SkyPilot job asynchronously.

    SkyPilot's sky.launch() is a blocking call. We run it in a thread pool
    via asyncio.to_thread() to avoid blocking the FastAPI event loop.
    (CONSTRAINT #2: No blocking I/O on the async event loop.)

    Args:
        job_id:   UUID of the job.
        job_type: "normal" (K3s → AWS) or "burst" (force AWS Spot).
        config:   Extra config from the API request payload.

    Returns:
        SkyPilot cluster name (used for log retrieval and autostop).
    """
    task = _build_task(job_id, job_type, config)
    cluster_name = f"virtuallab-{job_id[:8]}"

    logger.info(
        "Launching SkyPilot job | job_id=%s job_type=%s cluster=%s",
        job_id, job_type, cluster_name,
    )

    def _blocking_launch():
        """Blocking SkyPilot launch — runs in thread pool, not on event loop."""
        sky.launch(
            task,
            cluster_name=cluster_name,
            detach_run=False,   # Wait for job completion inside the thread
            retry_until_up=True,  # Retry on Spot preemption
        )
        return cluster_name

    # CONSTRAINT #2: run blocking SDK call in thread pool
    result = await asyncio.to_thread(_blocking_launch)

    logger.info(
        "SkyPilot job completed | job_id=%s cluster=%s", job_id, cluster_name
    )
    return result


async def get_job_logs(cluster_name: str) -> str:
    """
    Fetch logs from a SkyPilot cluster synchronously (called via thread pool).

    Used by the /api/logs/{job_id} SSE endpoint to stream logs to the UI.

    Args:
        cluster_name: The SkyPilot cluster name (e.g., "virtuallab-abc12345").

    Returns:
        Log output as a string.
    """
    def _blocking_logs():
        return sky.tail_logs(cluster_name, follow=False)

    return await asyncio.to_thread(_blocking_logs)


async def cancel_job(cluster_name: str) -> None:
    """
    Cancel a running SkyPilot job and tear down the cluster.

    Args:
        cluster_name: The SkyPilot cluster name to cancel and stop.
    """
    def _blocking_cancel():
        sky.cancel(cluster_name, all=True)
        sky.stop(cluster_name)

    logger.info("Cancelling SkyPilot job | cluster=%s", cluster_name)
    await asyncio.to_thread(_blocking_cancel)
    logger.info("SkyPilot job cancelled | cluster=%s", cluster_name)
