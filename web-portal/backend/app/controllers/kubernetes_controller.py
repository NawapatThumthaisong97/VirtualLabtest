"""
Kubernetes Controller
Business logic & orchestration for Kubernetes operations
"""
from typing import Dict, List, Any
import logging
from app.services import get_kubernetes_service
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class KubernetesController:
    """Controller สำหรับ Kubernetes operations"""
    
    @staticmethod
    def get_cluster_info() -> Dict[str, Any]:
        """ดึง cluster info ทั่วไป"""
        try:
            service = get_kubernetes_service()
            info = service.get_cluster_info()
            logger.info("Cluster info retrieved successfully")
            return info
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting cluster info: {e}")
            raise
    
    @staticmethod
    def get_namespaces() -> List[str]:
        """ดึง namespace ทั้งหมด"""
        try:
            service = get_kubernetes_service()
            namespaces = service.get_namespaces()
            logger.info(f"Retrieved {len(namespaces)} namespaces")
            return namespaces
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting namespaces: {e}")
            raise
    
    @staticmethod
    def get_pods(namespace: str = "default") -> List[Dict[str, Any]]:
        """ดึง Pod ทั้งหมดใน namespace"""
        try:
            service = get_kubernetes_service()
            pods = service.get_pods(namespace)
            logger.info(f"Retrieved {len(pods)} pods from namespace: {namespace}")
            return pods
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting pods: {e}")
            raise
    
    @staticmethod
    def get_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
        """ดึง Pod เดียว"""
        try:
            service = get_kubernetes_service()
            pod = service.get_pod(namespace, pod_name)
            logger.info(f"Retrieved pod: {pod_name} from namespace: {namespace}")
            return pod
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting pod {pod_name}: {e}")
            raise
    
    @staticmethod
    def get_deployments(namespace: str = "default") -> List[Dict[str, Any]]:
        """ดึง Deployment ทั้งหมด"""
        try:
            service = get_kubernetes_service()
            deployments = service.get_deployments(namespace)
            logger.info(f"Retrieved {len(deployments)} deployments from namespace: {namespace}")
            return deployments
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting deployments: {e}")
            raise
    
    @staticmethod
    def get_services(namespace: str = "default") -> List[Dict[str, Any]]:
        """ดึง Service ทั้งหมด"""
        try:
            service = get_kubernetes_service()
            services = service.get_services(namespace)
            logger.info(f"Retrieved {len(services)} services from namespace: {namespace}")
            return services
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting services: {e}")
            raise
    
    @staticmethod
    def get_nodes() -> List[Dict[str, Any]]:
        """ดึง Node ทั้งหมด"""
        try:
            service = get_kubernetes_service()
            nodes = service.get_nodes()
            logger.info(f"Retrieved {len(nodes)} nodes")
            return nodes
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting nodes: {e}")
            raise
    
    @staticmethod
    def delete_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
        """ลบ Pod"""
        try:
            service = get_kubernetes_service()
            result = service.delete_pod(namespace, pod_name)
            logger.info(f"Pod deleted: {pod_name} from namespace: {namespace}")
            return result
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error deleting pod {pod_name}: {e}")
            raise
    
    @staticmethod
    def delete_deployment(namespace: str, deployment_name: str) -> Dict[str, Any]:
        """ลบ Deployment"""
        try:
            service = get_kubernetes_service()
            result = service.delete_deployment(namespace, deployment_name)
            logger.info(f"Deployment deleted: {deployment_name} from namespace: {namespace}")
            return result
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error deleting deployment {deployment_name}: {e}")
            raise
    
    @staticmethod
    def get_pod_logs(namespace: str, pod_name: str, tail_lines: int = 100) -> str:
        """ดึง logs จาก Pod"""
        try:
            service = get_kubernetes_service()
            logs = service.get_logs(namespace, pod_name, tail_lines)
            logger.info(f"Retrieved logs from pod: {pod_name}")
            return logs
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error getting logs from pod {pod_name}: {e}")
            raise
    
    @staticmethod
    def create_deployment(namespace: str, manifest: Dict) -> Dict[str, Any]:
        """สร้าง Deployment จาก manifest"""
        try:
            service = get_kubernetes_service()
            result = service.create_deployment(namespace, manifest)
            logger.info(f"Deployment created: {result['name']} in namespace: {namespace}")
            return result
        except ApiException as e:
            logger.error(f"K8s API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Error creating deployment: {e}")
            raise
