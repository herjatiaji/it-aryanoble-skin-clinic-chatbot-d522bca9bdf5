from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CpuInfo(BaseModel):
    cores_logical: int = Field(..., description="Number of logical CPU cores on the host node")
    cores_physical: Optional[int] = Field(default=None, description="Number of physical CPU cores")
    architecture: str = Field(..., description="Processor architecture (e.g. x86_64)")
    model_name: Optional[str] = Field(default=None, description="CPU Model / Processor brand name")
    load_average_1m: Optional[float] = Field(default=None, description="1-minute load average")
    load_average_5m: Optional[float] = Field(default=None, description="5-minute load average")
    load_average_15m: Optional[float] = Field(default=None, description="15-minute load average")


class MemoryInfo(BaseModel):
    total_gb: float = Field(..., description="Total host node physical RAM in Gigabytes")
    available_gb: float = Field(..., description="Available physical RAM in Gigabytes")
    used_gb: float = Field(..., description="Used physical RAM in Gigabytes")
    used_percent: str = Field(..., description="RAM usage percentage")
    swap_total_gb: Optional[float] = Field(default=None, description="Total swap space in Gigabytes")
    swap_free_gb: Optional[float] = Field(default=None, description="Free swap space in Gigabytes")
    swap_used_percent: Optional[str] = Field(default=None, description="Swap usage percentage")


class ContainerCgroupInfo(BaseModel):
    is_cgroup_limited: bool = Field(default=False, description="Whether container/pod has specific resource limits")
    cgroup_version: Optional[str] = Field(default=None, description="cgroup version (v1 or v2)")
    memory_limit_gb: Optional[float] = Field(default=None, description="Explicit RAM limit for this container/pod in GB")
    memory_usage_gb: Optional[float] = Field(default=None, description="Current RAM usage inside this container/pod in GB")
    memory_usage_percent: Optional[str] = Field(default=None, description="Container RAM usage percentage against its limit")
    cpu_limit_cores: Optional[float] = Field(default=None, description="Container CPU quota/limit in cores (e.g. 2.0)")
    oom_kill_events: Optional[int] = Field(default=None, description="Number of OOM kill events recorded in this cgroup")


class DiskInfo(BaseModel):
    mount_point: str = Field(default="/", description="Root or target mount point")
    total_gb: float = Field(..., description="Total storage space in Gigabytes")
    used_gb: float = Field(..., description="Used storage space in Gigabytes")
    free_gb: float = Field(..., description="Free storage space in Gigabytes")
    used_percent: str = Field(..., description="Disk usage percentage")


class ProcessInfo(BaseModel):
    pid: int = Field(..., description="FastAPI process ID")
    memory_rss_mb: float = Field(..., description="Resident Set Size (RAM used by this Python process) in Megabytes")
    memory_vms_mb: Optional[float] = Field(default=None, description="Virtual Memory Size in Megabytes")
    uptime_seconds: float = Field(..., description="Process uptime in seconds")
    threads_count: Optional[int] = Field(default=None, description="Active threads count in this process")


class GpuInfo(BaseModel):
    cuda_available: bool = Field(..., description="Whether CUDA/GPU is available to PyTorch")
    device_count: int = Field(default=0, description="Number of detected GPU devices")
    devices: List[Dict[str, Any]] = Field(default_factory=list, description="List of GPU device specifications")


class SystemSpecsResponse(BaseModel):
    status: str = Field(default="success")
    timestamp: datetime = Field(..., description="UTC server timestamp")
    os_info: str = Field(..., description="Operating system release and kernel details")
    is_docker: bool = Field(..., description="Whether backend is running inside a Docker container or Kubernetes Pod")
    python_version: str = Field(..., description="Python runtime version")
    cpu: CpuInfo = Field(..., description="Host Node CPU specifications and load averages")
    ram: MemoryInfo = Field(..., description="Host Node RAM and Swap memory metrics")
    container_cgroup: ContainerCgroupInfo = Field(..., description="Container / Kubernetes Pod resource limits & usage")
    disk: DiskInfo = Field(..., description="Disk capacity and usage")
    process: ProcessInfo = Field(..., description="Current Python backend memory and uptime")
    gpu: GpuInfo = Field(..., description="GPU / CUDA hardware information")
