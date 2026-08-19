"""
SkyPilot Adapter
Adapter layer สำหรับจัดการการ submit และ monitor jobs บน SkyPilot
สำหรับ Cloud compute workloads (AI jobs, training, batch processing)
"""
from typing import Dict, List, Any, Optional, Tuple
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import subprocess
import json
import re
import tempfile
import os

try:
    from sky import cli as sky_cli
    from sky import task as sky_task
    from sky import jobs as sky_jobs
    SKY_AVAILABLE = True
except ImportError:
    SKY_AVAILABLE = False
    sky_cli = None
    sky_task = None
    sky_jobs = None

from app.exceptions.domain import DomainError, ValidationError
from app.models.session import SessionStatus, ServiceType

logger = logging.getLogger(__name__)


class JobStatusEnum(str, Enum):
    """SkyPilot job status mapping"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class CloudTypeEnum(str, Enum):
    """Supported cloud providers"""
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    KUBERNETES = "kubernetes"
    LOCAL = "local"


@dataclass
class TaskConfig:
    """Configuration สำหรับ SkyPilot Task"""
    name: str
    command: str  # Shell command to run
    image: Optional[str] = None  # Docker image (optional, can use setup script)
    gpu: Optional[str] = None  # GPU type: "T4", "V100", etc. None = CPU only
    cpu: str = "2"  # Number of CPUs
    memory: str = "4"  # Memory in GB
    disk_size: str = "20"  # Disk size in GB
    cloud_type: CloudTypeEnum = CloudTypeEnum.AWS
    region: Optional[str] = None  # Cloud region
    zones: Optional[List[str]] = None  # Specific zones
    env_vars: Dict[str, str] = field(default_factory=dict)
    setup_commands: List[str] = field(default_factory=list)
    install_dependencies: bool = False
    output_dir: Optional[str] = None  # Directory for outputs
    timeout_minutes: int = 60  # Job timeout
    
    def validate(self):
        """Validate TaskConfig"""
        if not self.name:
            raise ValidationError("Task name is required")
        if not self.command:
            raise ValidationError("Command is required")
        if not isinstance(self.cloud_type, CloudTypeEnum):
            raise ValidationError("Invalid cloud type")
        if int(self.cpu) < 1:
            raise ValidationError("CPU must be at least 1")
        if int(self.memory) < 1:
            raise ValidationError("Memory must be at least 1 GB")
        if int(self.timeout_minutes) < 1:
            raise ValidationError("Timeout must be at least 1 minute")


@dataclass
class ClusterConfig:
    """Configuration สำหรับ SkyPilot Cluster"""
    name: str
    cloud_type: CloudTypeEnum = CloudTypeEnum.AWS
    region: Optional[str] = None
    num_nodes: int = 1
    gpu_per_node: Optional[str] = None  # GPU type, e.g., "T4", "V100"
    cpu_per_node: str = "4"
    memory_per_node: str = "16"
    disk_size: str = "100"
    idle_minutes_to_down: int = 30
    env_vars: Dict[str, str] = field(default_factory=dict)
    
    def validate(self):
        """Validate ClusterConfig"""
        if not self.name:
            raise ValidationError("Cluster name is required")
        if self.num_nodes < 1:
            raise ValidationError("Number of nodes must be at least 1")
        if int(self.cpu_per_node) < 1:
            raise ValidationError("CPU per node must be at least 1")


class SkyPilotAdapter:
    """
    Adapter สำหรับ SkyPilot operations
    ทำหน้าที่แปลง Session/Business logic เป็น SkyPilot configuration
    """
    
    def __init__(self, use_cli: bool = True):
        """
        Initialize SkyPilot adapter
        
        Args:
            use_cli: If True, use CLI commands via subprocess. 
                    If False, use Python API (requires sky module)
        """
        self.use_cli = use_cli
        
        if use_cli:
            self._check_skypilot_cli_installed()
            logger.info("SkyPilotAdapter initialized (CLI mode)")
        else:
            if not SKY_AVAILABLE:
                raise DomainError(
                    "SkyPilot Python API not available. "
                    "Install with: pip install skypilot"
                )
            logger.info("SkyPilotAdapter initialized (Python API mode)")
    
    def submit_job(self, config: TaskConfig, cluster_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Submit a job to SkyPilot
        
        Args:
            config: TaskConfig instance
            cluster_name: Optional cluster name to use. If None, creates on-demand
            
        Returns:
            Dictionary with job submission result containing job_id
            
        Raises:
            ValidationError: If config is invalid
            DomainError: If submission fails
        """
        try:
            config.validate()
            
            # Generate task YAML
            task_yaml = self._generate_task_yaml(config)
            
            # Build sky submit command
            cmd = self._build_submit_command(config, task_yaml, cluster_name)
            
            # Execute sky submit
            result = self._execute_command(cmd)
            
            # Parse job ID from output
            job_id = self._parse_job_id(result)
            
            logger.info(f"Job submitted: {config.name} (Job ID: {job_id})")
            
            return {
                "status": "submitted",
                "job_name": config.name,
                "job_id": job_id,
                "cluster_name": cluster_name or "on-demand",
                "submitted_at": datetime.utcnow().isoformat()
            }
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error submitting job: {e}")
            raise DomainError(f"Failed to submit job: {str(e)}")
    
    def create_cluster(self, config: ClusterConfig) -> Dict[str, Any]:
        """
        Create a SkyPilot cluster
        
        Args:
            config: ClusterConfig instance
            
        Returns:
            Dictionary with cluster creation result
            
        Raises:
            ValidationError: If config is invalid
            DomainError: If creation fails
        """
        try:
            config.validate()
            
            # Build cluster YAML
            cluster_yaml = self._generate_cluster_yaml(config)
            
            # Build sky launch command
            cmd = self._build_cluster_command(config, cluster_yaml)
            
            # Execute command
            result = self._execute_command(cmd)
            
            logger.info(f"Cluster created: {config.name}")
            
            return {
                "status": "created",
                "cluster_name": config.name,
                "num_nodes": config.num_nodes,
                "cloud_type": config.cloud_type.value,
                "created_at": datetime.utcnow().isoformat()
            }
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error creating cluster: {e}")
            raise DomainError(f"Failed to create cluster: {str(e)}")
    
    def get_job_status(self, job_id: int, cluster_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get job status from SkyPilot
        
        Args:
            job_id: SkyPilot job ID
            cluster_name: Cluster name (optional for job lookup)
            
        Returns:
            Dictionary with job status
        """
        try:
            cmd = ["sky", "queue", "-r", str(job_id)]
            if cluster_name:
                cmd.extend(["--cluster", cluster_name])
            
            result = self._execute_command(cmd)
            status = self._parse_job_status(result)
            
            return {
                "job_id": job_id,
                "status": status,
                "queried_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            raise DomainError(f"Failed to get job status: {str(e)}")
    
    def cancel_job(self, job_id: int, cluster_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Cancel a job in SkyPilot
        
        Args:
            job_id: SkyPilot job ID
            cluster_name: Cluster name (optional)
            
        Returns:
            Dictionary with cancellation result
        """
        try:
            cmd = ["sky", "cancel", str(job_id), "-y"]
            if cluster_name:
                cmd.extend(["--cluster", cluster_name])
            
            result = self._execute_command(cmd)
            
            logger.info(f"Job cancelled: {job_id}")
            
            return {
                "status": "cancelled",
                "job_id": job_id,
                "cancelled_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            raise DomainError(f"Failed to cancel job: {str(e)}")
    
    def get_job_logs(self, job_id: int, cluster_name: Optional[str] = None, tail_lines: int = 100) -> str:
        """
        Get job logs from SkyPilot
        
        Args:
            job_id: SkyPilot job ID
            cluster_name: Cluster name (optional)
            tail_lines: Number of lines to tail
            
        Returns:
            Job logs as string
        """
        try:
            cmd = ["sky", "logs", str(job_id), "--tail", str(tail_lines)]
            if cluster_name:
                cmd.extend(["--cluster", cluster_name])
            
            result = self._execute_command(cmd)
            return result
        except Exception as e:
            logger.error(f"Error getting job logs: {e}")
            raise DomainError(f"Failed to get job logs: {str(e)}")
    
    def list_clusters(self) -> List[Dict[str, Any]]:
        """
        List all SkyPilot clusters
        
        Returns:
            List of cluster information
        """
        try:
            cmd = ["sky", "status"]
            result = self._execute_command(cmd)
            clusters = self._parse_cluster_list(result)
            
            return clusters
        except Exception as e:
            logger.error(f"Error listing clusters: {e}")
            raise DomainError(f"Failed to list clusters: {str(e)}")
    
    def terminate_cluster(self, cluster_name: str, force: bool = False) -> Dict[str, Any]:
        """
        Terminate a SkyPilot cluster
        
        Args:
            cluster_name: Name of cluster to terminate
            force: Force termination without confirmation
            
        Returns:
            Dictionary with termination result
        """
        try:
            cmd = ["sky", "down", cluster_name]
            if force:
                cmd.append("-y")
            
            result = self._execute_command(cmd)
            
            logger.info(f"Cluster terminated: {cluster_name}")
            
            return {
                "status": "terminated",
                "cluster_name": cluster_name,
                "terminated_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error terminating cluster: {e}")
            raise DomainError(f"Failed to terminate cluster: {str(e)}")
    
    # Helper methods
    def _check_skypilot_cli_installed(self):
        """Check if SkyPilot CLI is installed"""
        try:
            self._execute_command(["sky", "--version"])
        except Exception:
            raise DomainError("SkyPilot CLI not installed. Install with: pip install skypilot")
    
    def _execute_command(self, cmd: List[str]) -> str:
        """
        Execute shell command and return output
        
        Args:
            cmd: Command and arguments as list
            
        Returns:
            Command output as string
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
                raise DomainError(f"Command failed: {result.stderr}")
            
            return result.stdout
        except subprocess.TimeoutExpired:
            raise DomainError("Command execution timeout")
        except Exception as e:
            raise DomainError(f"Command execution failed: {str(e)}")
    
    def _generate_task_yaml(self, config: TaskConfig) -> str:
        """Generate SkyPilot task YAML"""
        yaml_content = f"""name: {config.name}

resources:
  cloud: {config.cloud_type.value}
  region: {config.region or 'any'}
  cpu: {config.cpu}
  memory: {config.memory}
  disk_size: {config.disk_size}
"""
        
        if config.gpu:
            yaml_content += f"  gpus: 1\n  gpu_name: {config.gpu}\n"
        
        if config.image:
            yaml_content += f"\nsetup: |\n  docker pull {config.image}\n"
        
        if config.setup_commands:
            yaml_content += "\nsetup: |\n"
            for cmd in config.setup_commands:
                yaml_content += f"  {cmd}\n"
        
        yaml_content += f"\nrun: |\n"
        
        # Add env vars
        if config.env_vars:
            for key, value in config.env_vars.items():
                yaml_content += f"  export {key}='{value}'\n"
        
        yaml_content += f"  {config.command}\n"
        
        return yaml_content
    
    def _generate_cluster_yaml(self, config: ClusterConfig) -> str:
        """Generate SkyPilot cluster YAML"""
        yaml_content = f"""cluster_name: {config.name}

cloud: {config.cloud_type.value}
region: {config.region or 'any'}

num_nodes: {config.num_nodes}

node_config:
  cloud: {config.cloud_type.value}
  region: {config.region or 'any'}
  cpu: {config.cpu_per_node}
  memory: {config.memory_per_node}
  disk_size: {config.disk_size}
"""
        
        if config.gpu_per_node:
            yaml_content += f"  gpus: 1\n  gpu_name: {config.gpu_per_node}\n"
        
        yaml_content += f"\ndown_minutes: {config.idle_minutes_to_down}\n"
        
        return yaml_content
    
    def _build_submit_command(
        self,
        config: TaskConfig,
        task_yaml: str,
        cluster_name: Optional[str]
    ) -> List[str]:
        """Build sky submit command"""
        # Save task YAML to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(task_yaml)
            yaml_path = f.name
        
        cmd = ["sky", "submit", yaml_path]
        
        if cluster_name:
            cmd.extend(["-c", cluster_name])
        
        return cmd
    
    def _build_cluster_command(self, config: ClusterConfig, cluster_yaml: str) -> List[str]:
        """Build sky launch/cluster command"""
        # Save cluster YAML to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(cluster_yaml)
            yaml_path = f.name
        
        return ["sky", "launch", yaml_path, "-c", config.name]
    
    def _parse_job_id(self, output: str) -> int:
        """Parse job ID from sky submit output"""
        # Example output: "Submitted job with ID 123"
        match = re.search(r"ID (\d+)", output)
        if match:
            return int(match.group(1))
        
        # Try alternative patterns
        match = re.search(r"job[_\s]+id[=:\s]+(\d+)", output, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        raise DomainError("Failed to extract job ID from submission output")
    
    def _parse_job_status(self, output: str) -> str:
        """Parse job status from sky queue output"""
        # Look for status line
        for line in output.split('\n'):
            if any(status in line for status in ['RUNNING', 'PENDING', 'SUCCEEDED', 'FAILED']):
                return line.strip()
        
        return JobStatusEnum.UNKNOWN.value
    
    def _parse_cluster_list(self, output: str) -> List[Dict[str, Any]]:
        """Parse cluster list from sky status output"""
        clusters = []
        
        # Parse output lines (basic parsing, might need adjustment based on actual format)
        for line in output.split('\n')[1:]:  # Skip header
            if line.strip() and not line.startswith('-'):
                parts = line.split()
                if len(parts) >= 2:
                    clusters.append({
                        "name": parts[0],
                        "status": parts[1] if len(parts) > 1 else "unknown"
                    })
        
        return clusters
