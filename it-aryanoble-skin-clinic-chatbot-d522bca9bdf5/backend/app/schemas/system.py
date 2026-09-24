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


class StageLatencyMetric(BaseModel):
    stage: str = Field(..., description="Stage name")
    duration_ms: float = Field(..., description="Wall-clock duration in milliseconds")
    percentage_of_total: str = Field(default="0.0%", description="Percentage contribution to total response time")
    cpu_time_ms: float = Field(default=0.0, description="CPU compute time consumed in milliseconds")
    cpu_utilization_percent: str = Field(default="0.0%", description="CPU utilization percentage during this stage")
    memory_rss_mb: float = Field(default=0.0, description="Process RAM RSS at the end of this stage in MB")
    memory_delta_mb: float = Field(default=0.0, description="Memory change (+/- MB) caused by this stage")
    status: str = Field(default="ok", description="Status: ok, warning, error, skipped")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Detailed stage stats")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class ResourceIntensitySummary(BaseModel):
    slowest_stage_name: str = Field(..., description="Stage taking the longest clock time")
    slowest_stage_duration_ms: float = Field(..., description="Duration of slowest stage in ms")
    slowest_stage_share: str = Field(..., description="Percentage of total time spent in slowest stage")
    most_cpu_intensive_stage: str = Field(..., description="Stage that consumed the most CPU compute time")
    most_memory_intensive_stage: str = Field(..., description="Stage that caused the biggest RAM increase")
    container_ram_limit_gb: Optional[float] = Field(default=None, description="Container RAM limit in GB")
    container_ram_used_gb: Optional[float] = Field(default=None, description="Container current RAM usage in GB")
    container_ram_headroom_gb: Optional[float] = Field(default=None, description="Remaining RAM headroom before container OOM")


class EndToEndPerformanceResponse(BaseModel):
    status: str = Field(default="success")
    timestamp: datetime = Field(..., description="UTC timestamp of test")
    test_query: str = Field(..., description="Query used for end-to-end benchmark")
    total_elapsed_ms: float = Field(..., description="Total elapsed benchmark time in milliseconds")
    primary_bottleneck: str = Field(..., description="Detected primary bottleneck")
    resource_intensity: ResourceIntensitySummary = Field(..., description="Summary of which stages stress CPU, RAM, and Latency the most")
    system_summary: Dict[str, Any] = Field(..., description="Quick summary of CPU, RAM, CUDA status")
    stages: List[StageLatencyMetric] = Field(..., description="Latency & Resource breakdown for each pipeline stage")
    recommendations: List[str] = Field(..., description="Actionable recommendations based on benchmark metrics")


class EventLoopHealth(BaseModel):
    is_responsive: bool = Field(..., description="Whether asyncio event loop is non-blocking")
    lag_ms: float = Field(..., description="Event loop scheduling lag in milliseconds")
    status: str = Field(..., description="Health status (ok, warning, critical)")


class DbPoolHealth(BaseModel):
    pool_size: int = Field(..., description="Configured SQLAlchemy connection pool size")
    checked_in: int = Field(..., description="Idle connections available in pool")
    checked_out: int = Field(..., description="Active in-use connections")
    overflow: int = Field(..., description="Overflow connections above pool size")
    concurrent_checkout_5_conns_ms: float = Field(..., description="Time to checkout 5 connections concurrently in ms")
    status: str = Field(..., description="Health status (ok, warning, critical)")


class EgressNetworkTarget(BaseModel):
    target: str = Field(..., description="Target hostname or endpoint (e.g. api.openai.com)")
    dns_lookup_ms: float = Field(..., description="DNS resolution time in ms")
    tcp_tls_handshake_ms: float = Field(..., description="TCP + TLS handshake time in ms")
    ttfb_ms: float = Field(..., description="Time to first byte in ms")
    status_code: Optional[int] = Field(default=None, description="HTTP response code")
    status: str = Field(..., description="Status (ok, warning, error)")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class RequestProxyInspection(BaseModel):
    http_version: str = Field(..., description="HTTP protocol version (e.g. 1.1, 2)")
    client_ip: str = Field(..., description="Detected client IP")
    is_behind_reverse_proxy: bool = Field(..., description="Whether request passed through Nginx/ALB/Cloudflare")
    proxy_headers_detected: Dict[str, str] = Field(..., description="Detected proxy headers")


class InfrastructureDiagnosticResponse(BaseModel):
    status: str = Field(default="success")
    timestamp: datetime = Field(..., description="UTC server timestamp")
    event_loop: EventLoopHealth = Field(..., description="AsyncIO event loop lag & blocking status")
    database_pool: DbPoolHealth = Field(..., description="SQLAlchemy connection pool capacity & checkout speed")
    egress_network: List[EgressNetworkTarget] = Field(..., description="DNS, TCP/TLS, and TTFB latencies to external cloud endpoints")
    request_proxy: RequestProxyInspection = Field(..., description="Reverse proxy and HTTP protocol inspection")
    active_threads: int = Field(..., description="Active Python threads count")
    diagnosis: List[str] = Field(..., description="Actionable findings & diagnosis from infrastructure tests")
