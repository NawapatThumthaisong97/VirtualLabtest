from fastapi import APIRouter, HTTPException, Query
from app.controllers.kubernetes_controller import KubernetesController
from kubernetes.client.rest import ApiException
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/cluster-info")
async def get_cluster_info():
    """ดึง cluster info ทั่วไป"""
    return KubernetesController.get_cluster_info()

@router.get("/namespaces")
async def list_namespaces():
    """ดึง namespace ทั้งหมด"""
    namespaces = KubernetesController.get_namespaces()
    return {"namespaces": namespaces}

@router.get("/pods")
async def list_pods(namespace: str = Query("default")):
    """ดึง Pod ทั้งหมดใน namespace"""
    pods = KubernetesController.get_pods(namespace)
    return {"namespace": namespace, "pods": pods}

@router.get("/pods/{pod_name}")
async def get_pod(pod_name: str, namespace: str = Query("default")):
    """ดึง Pod เดียว"""
    return KubernetesController.get_pod(namespace, pod_name)

@router.get("/deployments")
async def list_deployments(namespace: str = Query("default")):
    """ดึง Deployment ทั้งหมด"""
    deployments = KubernetesController.get_deployments(namespace)
    return {"namespace": namespace, "deployments": deployments}

@router.get("/services")
async def list_services(namespace: str = Query("default")):
    """ดึง Service ทั้งหมด"""
    services = KubernetesController.get_services(namespace)
    return {"namespace": namespace, "services": services}

@router.get("/nodes")
async def list_nodes():
    """ดึง Node ทั้งหมด"""
    nodes = KubernetesController.get_nodes()
    return {"nodes": nodes}

@router.delete("/pods/{pod_name}")
async def delete_pod(pod_name: str, namespace: str = Query("default")):
    """ลบ Pod"""
    return KubernetesController.delete_pod(namespace, pod_name)

@router.delete("/deployments/{deployment_name}")
async def delete_deployment(deployment_name: str, namespace: str = Query("default")):
    """ลบ Deployment"""
    return KubernetesController.delete_deployment(namespace, deployment_name)

@router.get("/pods/{pod_name}/logs")
async def get_pod_logs(pod_name: str, namespace: str = Query("default"), tail_lines: int = Query(100)):
    """ดึง logs จาก Pod"""
    logs = KubernetesController.get_pod_logs(namespace, pod_name, tail_lines)
    return {"pod": pod_name, "namespace": namespace, "logs": logs}
