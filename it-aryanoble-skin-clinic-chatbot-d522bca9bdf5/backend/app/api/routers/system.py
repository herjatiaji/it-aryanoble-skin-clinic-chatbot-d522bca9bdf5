import os
import sys
import time
import shutil
import platform
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, status
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from app.schemas.system import (
    SystemSpecsResponse,
    CpuInfo,
    MemoryInfo,
    ContainerCgroupInfo,
    DiskInfo,
    ProcessInfo,
    GpuInfo,
)

router = APIRouter(prefix="/system", tags=["System Diagnostics"])

_PROCESS_START_TIME = time.time()


def _get_cpu_model_name() -> Optional[str]:
    """Extracts CPU model name on Linux via /proc/cpuinfo or fallback to platform.processor()."""
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
    proc = platform.processor()
    return proc if proc else None


def _get_load_averages() -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Retrieves 1m, 5m, 15m load averages on Unix/Linux systems."""
    try:
        if hasattr(os, "getloadavg"):
            l1, l5, l15 = os.getloadavg()
            return round(l1, 2), round(l5, 2), round(l15, 2)
    except Exception:
        pass
    return None, None, None


def _get_memory_info() -> MemoryInfo:
    """Extracts RAM and Swap usage across Linux (/proc/meminfo) or fallback."""
    total_gb = 0.0
    available_gb = 0.0
    used_gb = 0.0
    used_percent = "0.0%"
    swap_total_gb = None
    swap_free_gb = None
    swap_used_percent = None

    # Linux /proc/meminfo (Standard Docker & Linux deployment)
    if os.path.exists("/proc/meminfo"):
        try:
            mem = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val_str = parts[1].strip().split()[0]
                        if val_str.isdigit():
                            mem[key] = int(val_str)

            total_kb = mem.get("MemTotal", 0)
            avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0) + mem.get("Buffers", 0) + mem.get("Cached", 0))
            used_kb = max(0, total_kb - avail_kb)

            if total_kb > 0:
                total_gb = round(total_kb / (1024 * 1024), 2)
                available_gb = round(avail_kb / (1024 * 1024), 2)
                used_gb = round(used_kb / (1024 * 1024), 2)
                used_percent = f"{round((used_kb / total_kb) * 100, 1)}%"

            sw_total_kb = mem.get("SwapTotal", 0)
            sw_free_kb = mem.get("SwapFree", 0)
            if sw_total_kb > 0:
                sw_used_kb = sw_total_kb - sw_free_kb
                swap_total_gb = round(sw_total_kb / (1024 * 1024), 2)
                swap_free_gb = round(sw_free_kb / (1024 * 1024), 2)
                swap_used_percent = f"{round((sw_used_kb / sw_total_kb) * 100, 1)}%"
            else:
                swap_total_gb = 0.0
                swap_free_gb = 0.0
                swap_used_percent = "0.0%"

            return MemoryInfo(
                total_gb=total_gb,
                available_gb=available_gb,
                used_gb=used_gb,
                used_percent=used_percent,
                swap_total_gb=swap_total_gb,
                swap_free_gb=swap_free_gb,
                swap_used_percent=swap_used_percent,
            )
        except Exception as err:
            logger.debug(f"Failed to read /proc/meminfo: {err}")

    # Fallback if psutil is available
    try:
        import psutil
        vmem = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return MemoryInfo(
            total_gb=round(vmem.total / (1024**3), 2),
            available_gb=round(vmem.available / (1024**3), 2),
            used_gb=round(vmem.used / (1024**3), 2),
            used_percent=f"{vmem.percent}%",
            swap_total_gb=round(sw.total / (1024**3), 2),
            swap_free_gb=round(sw.free / (1024**3), 2),
            swap_used_percent=f"{sw.percent}%",
        )
    except ImportError:
        pass

    return MemoryInfo(
        total_gb=total_gb,
        available_gb=available_gb,
        used_gb=used_gb,
        used_percent=used_percent,
    )


def _get_container_cgroup_info() -> ContainerCgroupInfo:
    """
    Inspects container / Kubernetes Pod cgroups (v1 and v2) to detect:
    - Explicit memory limits (cgroup memory.max / memory.limit_in_bytes)
    - Container memory usage
    - CPU quota (cpu.max / cpu.cfs_quota_us)
    - OOM kill events
    """
    # 1. Check cgroups v2 (Modern Docker & Kubernetes)
    if os.path.exists("/sys/fs/cgroup/memory.max"):
        try:
            mem_max_str = open("/sys/fs/cgroup/memory.max", "r").read().strip()
            mem_cur_str = open("/sys/fs/cgroup/memory.current", "r").read().strip() if os.path.exists("/sys/fs/cgroup/memory.current") else None
            
            mem_limit_gb = None
            mem_usage_gb = None
            mem_pct = None
            is_limited = False

            if mem_cur_str and mem_cur_str.isdigit():
                mem_usage_gb = round(int(mem_cur_str) / (1024**3), 2)

            if mem_max_str.isdigit():
                limit_bytes = int(mem_max_str)
                # If less than 1 Petabyte, it is an explicit cgroup container limit
                if limit_bytes < 1024**5:
                    mem_limit_gb = round(limit_bytes / (1024**3), 2)
                    is_limited = True
                    if mem_usage_gb is not None and mem_limit_gb > 0:
                        mem_pct = f"{round((mem_usage_gb / mem_limit_gb) * 100, 1)}%"

            cpu_limit_cores = None
            if os.path.exists("/sys/fs/cgroup/cpu.max"):
                cpu_max_line = open("/sys/fs/cgroup/cpu.max", "r").read().strip().split()
                if len(cpu_max_line) >= 2 and cpu_max_line[0].isdigit() and cpu_max_line[1].isdigit():
                    quota = int(cpu_max_line[0])
                    period = int(cpu_max_line[1])
                    if period > 0:
                        cpu_limit_cores = round(quota / period, 2)
                        is_limited = True

            oom_kills = None
            if os.path.exists("/sys/fs/cgroup/memory.events"):
                for line in open("/sys/fs/cgroup/memory.events", "r"):
                    if line.startswith("oom_kill"):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            oom_kills = int(parts[1])

            return ContainerCgroupInfo(
                is_cgroup_limited=is_limited,
                cgroup_version="v2",
                memory_limit_gb=mem_limit_gb,
                memory_usage_gb=mem_usage_gb,
                memory_usage_percent=mem_pct,
                cpu_limit_cores=cpu_limit_cores,
                oom_kill_events=oom_kills,
            )
        except Exception as e:
            logger.debug(f"cgroups v2 inspection failed: {e}")

    # 2. Check cgroups v1 (Legacy Docker & Kubernetes)
    if os.path.exists("/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            mem_lim_str = open("/sys/fs/cgroup/memory/memory.limit_in_bytes", "r").read().strip()
            mem_usg_str = open("/sys/fs/cgroup/memory/memory.usage_in_bytes", "r").read().strip() if os.path.exists("/sys/fs/cgroup/memory/memory.usage_in_bytes") else None

            mem_limit_gb = None
            mem_usage_gb = None
            mem_pct = None
            is_limited = False

            if mem_usg_str and mem_usg_str.isdigit():
                mem_usage_gb = round(int(mem_usg_str) / (1024**3), 2)

            if mem_lim_str.isdigit():
                lim_bytes = int(mem_lim_str)
                # cgroups v1 default unconstrained value is ~9223372036854771712 (0x7FFFFFFFFFFFF000)
                if lim_bytes < 1024**5:
                    mem_limit_gb = round(lim_bytes / (1024**3), 2)
                    is_limited = True
                    if mem_usage_gb is not None and mem_limit_gb > 0:
                        mem_pct = f"{round((mem_usage_gb / mem_limit_gb) * 100, 1)}%"

            cpu_limit_cores = None
            if os.path.exists("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") and os.path.exists("/sys/fs/cgroup/cpu/cpu.cfs_period_us"):
                quota_str = open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "r").read().strip()
                period_str = open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", "r").read().strip()
                if quota_str.lstrip("-").isdigit() and period_str.isdigit():
                    quota = int(quota_str)
                    period = int(period_str)
                    if quota > 0 and period > 0:
                        cpu_limit_cores = round(quota / period, 2)
                        is_limited = True

            return ContainerCgroupInfo(
                is_cgroup_limited=is_limited,
                cgroup_version="v1",
                memory_limit_gb=mem_limit_gb,
                memory_usage_gb=mem_usage_gb,
                memory_usage_percent=mem_pct,
                cpu_limit_cores=cpu_limit_cores,
                oom_kill_events=None,
            )
        except Exception as e:
            logger.debug(f"cgroups v1 inspection failed: {e}")

    return ContainerCgroupInfo(is_cgroup_limited=False)


def _get_process_memory() -> tuple[float, Optional[float]]:
    """Retrieves current Python process RSS (Resident Set Size) and VMS memory in MB."""
    rss_mb = 0.0
    vms_mb = None

    if os.path.exists("/proc/self/status"):
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_mb = round(int(line.split()[1]) / 1024, 2)
                    elif line.startswith("VmSize:"):
                        vms_mb = round(int(line.split()[1]) / 1024, 2)
            if rss_mb > 0:
                return rss_mb, vms_mb
        except Exception:
            pass

    try:
        import psutil
        proc = psutil.Process(os.getpid())
        mem = proc.memory_info()
        return round(mem.rss / (1024 * 1024), 2), round(mem.vms / (1024 * 1024), 2)
    except Exception:
        pass

    return rss_mb, vms_mb


def _get_gpu_info() -> GpuInfo:
    """Checks whether CUDA / PyTorch GPU acceleration is available."""
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        device_count = torch.cuda.device_count() if cuda_avail else 0
        devices = []
        if cuda_avail:
            for idx in range(device_count):
                props = torch.cuda.get_device_properties(idx)
                total_vram_gb = round(props.total_memory / (1024**3), 2)
                allocated_vram_gb = round(torch.cuda.memory_allocated(idx) / (1024**3), 2)
                devices.append({
                    "id": idx,
                    "name": props.name,
                    "total_vram_gb": total_vram_gb,
                    "allocated_vram_gb": allocated_vram_gb,
                    "compute_capability": f"{props.major}.{props.minor}",
                })
        return GpuInfo(
            cuda_available=cuda_avail,
            device_count=device_count,
            devices=devices
        )
    except Exception:
        return GpuInfo(cuda_available=False, device_count=0, devices=[])


@router.get("/specs", response_model=SystemSpecsResponse, status_code=status.HTTP_200_OK)
def get_system_specs() -> SystemSpecsResponse:
    """
    Returns complete live system specifications and resource usage:
    - Host Node OS details and Docker/Kubernetes Pod environment check
    - Container / Kubernetes Pod explicit Cgroup Limits (RAM Limit, CPU Quotas, OOM Events)
    - Logical & physical CPU cores with load averages
    - Physical RAM & Swap capacity and real-time usage
    - Primary disk space (Total, Used, Free)
    - Python process memory (RSS / VMS) and uptime
    - GPU / CUDA hardware availability
    """
    # 1. CPU
    logical_cores = os.cpu_count() or 1
    cpu_model = _get_cpu_model_name()
    l1, l5, l15 = _get_load_averages()

    cpu_info = CpuInfo(
        cores_logical=logical_cores,
        cores_physical=None,
        architecture=platform.machine() or "unknown",
        model_name=cpu_model,
        load_average_1m=l1,
        load_average_5m=l5,
        load_average_15m=l15,
    )

    # 2. Memory (Host Node)
    ram_info = _get_memory_info()

    # 3. Container / Kubernetes Pod Cgroup Limits
    cgroup_info = _get_container_cgroup_info()

    # 4. Disk Usage
    target_path = "/" if os.name != "nt" else os.path.splitdrive(os.getcwd())[0] or "C:\\"
    disk_stat = shutil.disk_usage(target_path)
    total_disk_gb = round(disk_stat.total / (1024**3), 2)
    used_disk_gb = round(disk_stat.used / (1024**3), 2)
    free_disk_gb = round(disk_stat.free / (1024**3), 2)
    disk_used_percent = f"{round((disk_stat.used / max(disk_stat.total, 1)) * 100, 1)}%"

    disk_info = DiskInfo(
        mount_point=target_path,
        total_gb=total_disk_gb,
        used_gb=used_disk_gb,
        free_gb=free_disk_gb,
        used_percent=disk_used_percent,
    )

    # 5. Python Process
    rss_mb, vms_mb = _get_process_memory()
    uptime_sec = round(time.time() - _PROCESS_START_TIME, 1)

    process_info = ProcessInfo(
        pid=os.getpid(),
        memory_rss_mb=rss_mb,
        memory_vms_mb=vms_mb,
        uptime_seconds=uptime_sec,
        threads_count=threading.active_count(),
    )

    # 6. GPU
    gpu_info = _get_gpu_info()

    # 7. Environment & Docker/Pod detection
    is_docker = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv") or "KUBERNETES_SERVICE_HOST" in os.environ
    os_str = f"{platform.system()} {platform.release()} ({platform.version()})"

    return SystemSpecsResponse(
        status="success",
        timestamp=datetime.now(timezone.utc),
        os_info=os_str,
        is_docker=is_docker,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        cpu=cpu_info,
        ram=ram_info,
        container_cgroup=cgroup_info,
        disk=disk_info,
        process=process_info,
        gpu=gpu_info,
    )
