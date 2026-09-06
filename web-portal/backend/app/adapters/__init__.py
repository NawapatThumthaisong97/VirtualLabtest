"""
adapters
Adapter layer for infrastructure interactions (Kubernetes, SkyPilot, etc.)
"""

from app.adapters.kubernetes_adapter import (
    KubernetesAdapter,
    PodConfig,
    DeploymentConfig,
    PodStatusEnum
)
from app.adapters.skypilot_adapter import (
    SkyPilotAdapter,
    TaskConfig,
    ClusterConfig,
    JobStatusEnum,
    CloudTypeEnum
)

__all__ = [
    # Kubernetes Adapter
    "KubernetesAdapter",
    "PodConfig",
    "DeploymentConfig",
    "PodStatusEnum",
    # SkyPilot Adapter
    "SkyPilotAdapter",
    "TaskConfig",
    "ClusterConfig",
    "JobStatusEnum",
    "CloudTypeEnum",
]
