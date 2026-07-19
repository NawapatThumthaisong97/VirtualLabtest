"""
Kubernetes Configuration Helper
"""
from pathlib import Path
from typing import Optional
import os
from .settings import settings


class K8sSettingsHelper:
    """Helper class สำหรับ Kubernetes settings"""
    
    @staticmethod
    def get_resolved_kubeconfig_path() -> Optional[str]:
        """
        Resolve kubeconfig path with fallback logic
        1. ใช้ KUBECONFIG_PATH จาก settings ถ้ามี
        2. ใช้ KUBECONFIG env variable ถ้ามี
        3. ใช้ default path ในโปรเจค (kubeconfig.yaml)
        4. ใช้ default path ของ kubectl (~/.kube/config)
        5. ถ้าไม่เจอ return None
        """
        # ตรวจสอบ settings config path ก่อน
        if settings.KUBECONFIG_PATH and Path(settings.KUBECONFIG_PATH).exists():
            return settings.KUBECONFIG_PATH
        
        # ตรวจสอบ env variable
        if env_kubeconfig := os.getenv('KUBECONFIG'):
            if Path(env_kubeconfig).exists():
                return env_kubeconfig
        
        # ตรวจสอบ project default path
        project_kubeconfig = Path(__file__).parent.parent.parent / 'kubeconfig.yaml'
        if project_kubeconfig.exists():
            return str(project_kubeconfig)
        
        # ใช้ default kubectl path
        default_kubeconfig = Path.home() / '.kube' / 'config'
        if default_kubeconfig.exists():
            return str(default_kubeconfig)
        
        # ถ้าไม่เจอไฟล์
        return None


def get_resolved_kubeconfig_path() -> Optional[str]:
    """Helper function สำหรับดึง resolved kubeconfig path"""
    return K8sSettingsHelper.get_resolved_kubeconfig_path()
