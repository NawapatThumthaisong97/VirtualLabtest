"""
Kubernetes Adapter
Adapter layer สำหรับจัดการการสร้างและลบ Pod/Deployment บน Kubernetes
สำหรับ Lab sessions และ Compute workloads
"""
from typing import Dict, List, Any, Optional
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from app.services.kubernetes_service import get_kubernetes_service, KubernetesService
from app.exceptions.domain import DomainError, ValidationError
from app.models.session import SessionStatus, ServiceType
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class PodStatusEnum(str, Enum):
    """Pod status mapping"""
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    UNKNOWN = "Unknown"


@dataclass
class PodConfig:
    """Configuration สำหรับ Pod deployment"""
    name: str
    namespace: str = "default"
    image: str = None
    image_pull_policy: str = "IfNotPresent"
    replicas: int = 1
    cpu_request: str = "100m"
    cpu_limit: str = "500m"
    memory_request: str = "128Mi"
    memory_limit: str = "512Mi"
    env_vars: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    node_selector: Optional[Dict[str, str]] = None
    ports: List[Dict[str, Any]] = field(default_factory=lambda: [{"containerPort": 8080}])
    
    def validate(self):
        """Validate PodConfig"""
        if not self.name:
            raise ValidationError("Pod name is required")
        if not self.image:
            raise ValidationError("Image is required")
        if not self.namespace:
            raise ValidationError("Namespace is required")
        if self.replicas < 1:
            raise ValidationError("Replicas must be at least 1")


@dataclass
class DeploymentConfig:
    """Configuration สำหรับ Deployment"""
    name: str
    namespace: str = "default"
    image: str = None
    image_pull_policy: str = "IfNotPresent"
    replicas: int = 1
    cpu_request: str = "100m"
    cpu_limit: str = "500m"
    memory_request: str = "128Mi"
    memory_limit: str = "512Mi"
    env_vars: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    node_selector: Optional[Dict[str, str]] = None
    ports: List[Dict[str, Any]] = field(default_factory=lambda: [{"containerPort": 8080}])
    
    def validate(self):
        """Validate DeploymentConfig"""
        if not self.name:
            raise ValidationError("Deployment name is required")
        if not self.image:
            raise ValidationError("Image is required")
        if not self.namespace:
            raise ValidationError("Namespace is required")
        if self.replicas < 1:
            raise ValidationError("Replicas must be at least 1")


class KubernetesAdapter:
    """
    Adapter สำหรับ Kubernetes operations
    ทำหน้าที่แปลง Session/Business logic เป็น K8s manifest
    """
    
    def __init__(self, k8s_service: Optional[KubernetesService] = None):
        """
        Initialize Kubernetes adapter
        
        Args:
            k8s_service: KubernetesService instance. If None, uses singleton
        """
        self.k8s_service = k8s_service or get_kubernetes_service()
        logger.info("KubernetesAdapter initialized")
    
    def create_pod(self, config: PodConfig) -> Dict[str, Any]:
        """
        Create a Pod from PodConfig
        
        Args:
            config: PodConfig instance
            
        Returns:
            Dictionary with pod creation result
            
        Raises:
            ValidationError: If config is invalid
            ApiException: If K8s API call fails
        """
        try:
            config.validate()
            
            # Build Pod manifest
            manifest = self._build_pod_manifest(config)
            
            # Create pod
            pod = self.k8s_service.v1.create_namespaced_pod(
                namespace=config.namespace,
                body=manifest
            )
            
            logger.info(f"Pod created: {config.name} in namespace {config.namespace}")
            
            return {
                "status": "created",
                "pod_name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "created_at": datetime.utcnow().isoformat()
            }
        except ValidationError:
            raise
        except ApiException as e:
            logger.error(f"K8s API error creating pod: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating pod: {e}")
            raise DomainError(f"Failed to create pod: {str(e)}")
    
    def create_deployment(self, config: DeploymentConfig) -> Dict[str, Any]:
        """
        Create a Deployment from DeploymentConfig
        
        Args:
            config: DeploymentConfig instance
            
        Returns:
            Dictionary with deployment creation result
            
        Raises:
            ValidationError: If config is invalid
            ApiException: If K8s API call fails
        """
        try:
            config.validate()
            
            # Build Deployment manifest
            manifest = self._build_deployment_manifest(config)
            
            # Create deployment
            deployment = self.k8s_service.apps_v1.create_namespaced_deployment(
                namespace=config.namespace,
                body=manifest
            )
            
            logger.info(f"Deployment created: {config.name} in namespace {config.namespace}")
            
            return {
                "status": "created",
                "deployment_name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "replicas": deployment.spec.replicas,
                "created_at": datetime.utcnow().isoformat()
            }
        except ValidationError:
            raise
        except ApiException as e:
            logger.error(f"K8s API error creating deployment: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating deployment: {e}")
            raise DomainError(f"Failed to create deployment: {str(e)}")
    
    def delete_pod(self, pod_name: str, namespace: str = "default") -> Dict[str, Any]:
        """
        Delete a Pod
        
        Args:
            pod_name: Name of the pod to delete
            namespace: Kubernetes namespace
            
        Returns:
            Dictionary with deletion result
        """
        try:
            self.k8s_service.v1.delete_namespaced_pod(pod_name, namespace)
            logger.info(f"Pod deleted: {pod_name} from namespace {namespace}")
            
            return {
                "status": "deleted",
                "pod_name": pod_name,
                "namespace": namespace,
                "deleted_at": datetime.utcnow().isoformat()
            }
        except ApiException as e:
            logger.error(f"K8s API error deleting pod: {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting pod: {e}")
            raise DomainError(f"Failed to delete pod: {str(e)}")
    
    def delete_deployment(self, deployment_name: str, namespace: str = "default") -> Dict[str, Any]:
        """
        Delete a Deployment
        
        Args:
            deployment_name: Name of the deployment to delete
            namespace: Kubernetes namespace
            
        Returns:
            Dictionary with deletion result
        """
        try:
            self.k8s_service.apps_v1.delete_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                propagation_policy="Foreground"  # Wait for pods to be deleted
            )
            logger.info(f"Deployment deleted: {deployment_name} from namespace {namespace}")
            
            return {
                "status": "deleted",
                "deployment_name": deployment_name,
                "namespace": namespace,
                "deleted_at": datetime.utcnow().isoformat()
            }
        except ApiException as e:
            logger.error(f"K8s API error deleting deployment: {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting deployment: {e}")
            raise DomainError(f"Failed to delete deployment: {str(e)}")
    
    def get_pod_status(self, pod_name: str, namespace: str = "default") -> Dict[str, Any]:
        """
        Get Pod status
        
        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace
            
        Returns:
            Dictionary with pod status
        """
        try:
            pod = self.k8s_service.v1.read_namespaced_pod(pod_name, namespace)
            
            return {
                "pod_name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "conditions": [
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason
                    }
                    for c in (pod.status.conditions or [])
                ],
                "container_statuses": [
                    {
                        "name": c.name,
                        "ready": c.ready,
                        "restart_count": c.restart_count
                    }
                    for c in (pod.status.container_statuses or [])
                ]
            }
        except ApiException as e:
            logger.error(f"K8s API error getting pod status: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting pod status: {e}")
            raise DomainError(f"Failed to get pod status: {str(e)}")
    
    def get_deployment_status(self, deployment_name: str, namespace: str = "default") -> Dict[str, Any]:
        """
        Get Deployment status
        
        Args:
            deployment_name: Name of the deployment
            namespace: Kubernetes namespace
            
        Returns:
            Dictionary with deployment status
        """
        try:
            deployment = self.k8s_service.apps_v1.read_namespaced_deployment(
                deployment_name,
                namespace
            )
            
            return {
                "deployment_name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "replicas": deployment.spec.replicas,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "updated_replicas": deployment.status.updated_replicas or 0,
                "available_replicas": deployment.status.available_replicas or 0
            }
        except ApiException as e:
            logger.error(f"K8s API error getting deployment status: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting deployment status: {e}")
            raise DomainError(f"Failed to get deployment status: {str(e)}")
    
    def get_pod_logs(self, pod_name: str, namespace: str = "default", tail_lines: int = 100) -> str:
        """
        Get logs from a Pod
        
        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace
            tail_lines: Number of lines to tail
            
        Returns:
            Pod logs as string
        """
        try:
            logs = self.k8s_service.v1.read_namespaced_pod_log(
                pod_name,
                namespace,
                tail_lines=tail_lines
            )
            return logs
        except ApiException as e:
            logger.error(f"K8s API error getting logs: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting pod logs: {e}")
            raise DomainError(f"Failed to get pod logs: {str(e)}")
    
    # Helper methods for building manifests
    def _build_pod_manifest(self, config: PodConfig) -> Dict[str, Any]:
        """Build Kubernetes Pod manifest from config"""
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": config.name,
                "namespace": config.namespace,
                "labels": config.labels or {}
            },
            "spec": {
                "containers": [
                    {
                        "name": config.name,
                        "image": config.image,
                        "imagePullPolicy": config.image_pull_policy,
                        "ports": config.ports,
                        "env": [
                            {"name": k, "value": str(v)}
                            for k, v in (config.env_vars or {}).items()
                        ],
                        "resources": {
                            "requests": {
                                "cpu": config.cpu_request,
                                "memory": config.memory_request
                            },
                            "limits": {
                                "cpu": config.cpu_limit,
                                "memory": config.memory_limit
                            }
                        }
                    }
                ],
                "nodeSelector": config.node_selector or {},
                "restartPolicy": "Never"
            }
        }
    
    def _build_deployment_manifest(self, config: DeploymentConfig) -> Dict[str, Any]:
        """Build Kubernetes Deployment manifest from config"""
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": config.name,
                "namespace": config.namespace,
                "labels": config.labels or {}
            },
            "spec": {
                "replicas": config.replicas,
                "selector": {
                    "matchLabels": {"app": config.name}
                },
                "template": {
                    "metadata": {
                        "labels": {"app": config.name, **(config.labels or {})}
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": config.name,
                                "image": config.image,
                                "imagePullPolicy": config.image_pull_policy,
                                "ports": config.ports,
                                "env": [
                                    {"name": k, "value": str(v)}
                                    for k, v in (config.env_vars or {}).items()
                                ],
                                "resources": {
                                    "requests": {
                                        "cpu": config.cpu_request,
                                        "memory": config.memory_request
                                    },
                                    "limits": {
                                        "cpu": config.cpu_limit,
                                        "memory": config.memory_limit
                                    }
                                }
                            }
                        ],
                        "nodeSelector": config.node_selector or {}
                    }
                }
            }
        }
