"""
Kubernetes Service
Business logic สำหรับ Kubernetes operations
"""
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import List, Dict, Any, Optional
import logging
import os
from app.configs import get_resolved_kubeconfig_path, settings

# Disable SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class KubernetesService:
    """Service สำหรับ Kubernetes operations"""
    
    def __init__(self, kubeconfig_path: Optional[str] = None):
        """
        Initialize Kubernetes service with kubeconfig
        
        Args:
            kubeconfig_path: Path to kubeconfig file. 
                           If None, uses resolved path from settings
        """
        # ใช้ resolved path ถ้าไม่ได้ระบุ path
        if not kubeconfig_path:
            kubeconfig_path = get_resolved_kubeconfig_path()
        
        if kubeconfig_path:
            if not os.path.exists(kubeconfig_path):
                raise FileNotFoundError(f"kubeconfig not found: {kubeconfig_path}")
            logger.info(f"Loading kubeconfig from: {kubeconfig_path}")
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            logger.info("Loading kubeconfig from default locations")
            config.load_kube_config()
        
        # Disable SSL verification for self-signed certificates (development)
        client.Configuration.get_default_copy().verify_ssl = False
        
        # Create API clients
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        
        logger.info("Kubernetes service initialized successfully")
    
    def get_pods(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """ดึง Pod ทั้งหมดในแต่ละ namespace"""
        try:
            pods = self.v1.list_namespaced_pod(namespace)
            return [{
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "namespace": pod.metadata.namespace,
                "restarts": pod.status.container_statuses[0].restart_count if pod.status.container_statuses else 0
            } for pod in pods.items]
        except ApiException as e:
            logger.error(f"Error fetching pods: {e}")
            raise
    
    def get_pod(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        """ดึง Pod เดียว"""
        try:
            pod = self.v1.read_namespaced_pod(pod_name, namespace)
            return {
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "namespace": pod.metadata.namespace,
                "labels": pod.metadata.labels,
                "containers": [c.name for c in pod.spec.containers]
            }
        except ApiException as e:
            logger.error(f"Error fetching pod {pod_name}: {e}")
            raise
    
    def get_deployments(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """ดึง Deployment ทั้งหมด"""
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace)
            return [{
                "name": dep.metadata.name,
                "replicas": dep.spec.replicas,
                "ready_replicas": dep.status.ready_replicas or 0,
                "updated_replicas": dep.status.updated_replicas or 0
            } for dep in deployments.items]
        except ApiException as e:
            logger.error(f"Error fetching deployments: {e}")
            raise
    
    def get_namespaces(self) -> List[str]:
        """ดึง namespace ทั้งหมด"""
        try:
            namespaces = self.v1.list_namespace()
            return [ns.metadata.name for ns in namespaces.items]
        except ApiException as e:
            logger.error(f"Error fetching namespaces: {e}")
            raise
    
    def get_nodes(self) -> List[Dict[str, Any]]:
        """ดึง Node ทั้งหมด"""
        try:
            nodes = self.v1.list_node()
            return [{
                "name": node.metadata.name,
                "status": node.status.conditions[-1].type if node.status.conditions else "Unknown",
                "ready": node.status.conditions[-1].status if node.status.conditions else "Unknown",
                "cpu": node.status.allocatable.get('cpu') if node.status.allocatable else None,
                "memory": node.status.allocatable.get('memory') if node.status.allocatable else None,
                "labels": node.metadata.labels,
            } for node in nodes.items]
        except ApiException as e:
            logger.error(f"Error fetching nodes: {e}")
            raise
    
    def get_services(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """ดึง Service ทั้งหมด"""
        try:
            services = self.v1.list_namespaced_service(namespace)
            return [{
                "name": svc.metadata.name,
                "type": svc.spec.type,
                "cluster_ip": svc.spec.cluster_ip,
                "ports": [{"port": p.port, "target_port": p.target_port} for p in svc.spec.ports]
            } for svc in services.items]
        except ApiException as e:
            logger.error(f"Error fetching services: {e}")
            raise
    
    def create_deployment(self, namespace: str, manifest: Dict) -> Dict:
        """สร้าง Deployment จาก manifest"""
        try:
            dep = self.apps_v1.create_namespaced_deployment(
                namespace=namespace,
                body=manifest
            )
            return {
                "status": "created",
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace
            }
        except ApiException as e:
            logger.error(f"Error creating deployment: {e}")
            raise
    
    def delete_pod(self, namespace: str, pod_name: str) -> Dict:
        """ลบ Pod"""
        try:
            self.v1.delete_namespaced_pod(pod_name, namespace)
            return {"status": "deleted", "pod": pod_name, "namespace": namespace}
        except ApiException as e:
            logger.error(f"Error deleting pod: {e}")
            raise
    
    def delete_deployment(self, namespace: str, deployment_name: str) -> Dict:
        """ลบ Deployment"""
        try:
            self.apps_v1.delete_namespaced_deployment(deployment_name, namespace)
            return {"status": "deleted", "deployment": deployment_name, "namespace": namespace}
        except ApiException as e:
            logger.error(f"Error deleting deployment: {e}")
            raise
    
    def get_logs(self, namespace: str, pod_name: str, tail_lines: int = 100) -> str:
        """ดึง logs จาก Pod"""
        try:
            logs = self.v1.read_namespaced_pod_log(
                pod_name, 
                namespace,
                tail_lines=tail_lines
            )
            return logs
        except ApiException as e:
            logger.error(f"Error fetching logs: {e}")
            raise
    
    def get_cluster_info(self) -> Dict[str, Any]:
        """ดึง cluster info"""
        try:
            nodes = self.v1.list_node()
            namespaces = self.v1.list_namespace()
            pods = self.v1.list_pod_for_all_namespaces()
            
            return {
                "nodes": len(nodes.items),
                "namespaces": len(namespaces.items),
                "pods": len(pods.items)
            }
        except ApiException as e:
            logger.error(f"Error fetching cluster info: {e}")
            raise


# Singleton instance cache
_k8s_service_instance = None


def get_kubernetes_service() -> KubernetesService:
    """Get or create Kubernetes service instance (singleton)"""
    global _k8s_service_instance
    
    if not settings.K8S_ENABLED:
        raise RuntimeError("K8s integration is disabled (K8S_ENABLED=False)")
    
    if _k8s_service_instance is None:
        _k8s_service_instance = KubernetesService()
    
    return _k8s_service_instance
