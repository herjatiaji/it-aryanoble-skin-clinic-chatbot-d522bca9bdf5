import os
import sys
import time
import shutil
import platform
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import asyncio
import socket
import httpx
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db, engine as core_db_engine, AsyncSessionLocal

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
    StageLatencyMetric,
    ResourceIntensitySummary,
    EndToEndPerformanceResponse,
    EventLoopHealth,
    DbPoolHealth,
    EgressNetworkTarget,
    RequestProxyInspection,
    InfrastructureDiagnosticResponse,
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


@router.get("/performance-check", response_model=EndToEndPerformanceResponse, status_code=status.HTTP_200_OK)
@router.post("/performance-check", response_model=EndToEndPerformanceResponse, status_code=status.HTTP_200_OK)
async def run_performance_check(
    query: str = Query("Apa indikasi dan cara pakai Acne Clarifying Gel?", description="Sample clinical query for benchmark"),
    include_reranker_test: bool = Query(True, description="Whether to benchmark the heavy CPU Cross-Encoder reranker"),
    db: AsyncSession = Depends(get_db),
) -> EndToEndPerformanceResponse:
    """
    End-to-End Diagnostic Benchmark for Backend & RAG Subsystem:
    - Measures exact per-stage latency in milliseconds (DB, Embedding, Vector Search, BM25, RRF, Cross-Encoder, LLM, S3).
    - Tracks per-stage CPU compute time (process_time), CPU utilization %, and RAM memory delta (RSS).
    - Identifies which specific resource (CPU, Memory, Network, DB) suffers the highest load.
    - Provides actionable performance recommendations.
    """
    t_start_total = time.perf_counter()
    raw_stage_records: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    # -------------------------------------------------------------
    # Stage 1: PostgreSQL Core Database Latency
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    rss_before, _ = _get_process_memory()
    status_st = "ok"
    err_str = None
    details = {"query": "SELECT 1"}
    try:
        res = await db.execute(text("SELECT 1"))
        res.scalar()
    except Exception as e:
        status_st = "error"
        err_str = str(e)
    t_dur = round((time.perf_counter() - t0) * 1000, 2)
    c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
    rss_after, _ = _get_process_memory()
    raw_stage_records.append({
        "stage": "postgresql_core_db_ping",
        "duration_ms": t_dur,
        "cpu_time_ms": c_dur,
        "memory_rss_mb": rss_after,
        "memory_delta_mb": round(rss_after - rss_before, 2),
        "status": status_st if t_dur < 50 or status_st == "error" else "warning",
        "details": details,
        "error": err_str
    })

    # -------------------------------------------------------------
    # Stage 2: Dense Embedding API / Model Latency
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    rss_before, _ = _get_process_memory()
    status_st = "ok"
    err_str = None
    query_vector = None
    details = {}
    try:
        from app.rag.services.embeddings import EmbeddingFactory
        emb_adapter = EmbeddingFactory.get_embeddings_adapter()
        query_vector = await asyncio.to_thread(emb_adapter.embed_query, query)
        details = {
            "model": getattr(emb_adapter, "model_name", "unknown"),
            "dimension": len(query_vector) if query_vector else 0,
        }
    except Exception as e:
        status_st = "error"
        err_str = str(e)
    t_dur = round((time.perf_counter() - t0) * 1000, 2)
    c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
    rss_after, _ = _get_process_memory()
    raw_stage_records.append({
        "stage": "dense_embedding_generation",
        "duration_ms": t_dur,
        "cpu_time_ms": c_dur,
        "memory_rss_mb": rss_after,
        "memory_delta_mb": round(rss_after - rss_before, 2),
        "status": status_st if t_dur < 1000 or status_st == "error" else "warning",
        "details": details,
        "error": err_str
    })

    # -------------------------------------------------------------
    # Stage 3: PGVector Vector Store Similarity Search
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    rss_before, _ = _get_process_memory()
    status_st = "ok"
    err_str = None
    dense_hits = []
    details = {}
    try:
        from app.rag.services.factory import AdapterFactory
        vector_store = AdapterFactory.get_vector_store()
        dense_hits = await asyncio.to_thread(vector_store.search, query, 5, None)
        details = {"hits_count": len(dense_hits) if dense_hits else 0}
    except Exception as e:
        status_st = "error"
        err_str = str(e)
    t_dur = round((time.perf_counter() - t0) * 1000, 2)
    c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
    rss_after, _ = _get_process_memory()
    raw_stage_records.append({
        "stage": "pgvector_similarity_search",
        "duration_ms": t_dur,
        "cpu_time_ms": c_dur,
        "memory_rss_mb": rss_after,
        "memory_delta_mb": round(rss_after - rss_before, 2),
        "status": status_st if t_dur < 300 or status_st == "error" else "warning",
        "details": details,
        "error": err_str
    })

    # -------------------------------------------------------------
    # Stage 4: BM25 Sparse Search
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    rss_before, _ = _get_process_memory()
    status_st = "ok"
    err_str = None
    sparse_hits = []
    details = {}
    try:
        from app.rag.services.factory import AdapterFactory
        bm25_index = AdapterFactory.get_bm25_index()
        sparse_hits = await asyncio.to_thread(bm25_index.search, query, 5, None, True)
        doc_count = len(bm25_index.doc_ids) if hasattr(bm25_index, "doc_ids") else 0
        details = {"hits_count": len(sparse_hits) if sparse_hits else 0, "indexed_chunks": doc_count}
    except Exception as e:
        status_st = "error"
        err_str = str(e)
    t_dur = round((time.perf_counter() - t0) * 1000, 2)
    c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
    rss_after, _ = _get_process_memory()
    raw_stage_records.append({
        "stage": "bm25_sparse_search",
        "duration_ms": t_dur,
        "cpu_time_ms": c_dur,
        "memory_rss_mb": rss_after,
        "memory_delta_mb": round(rss_after - rss_before, 2),
        "status": status_st if t_dur < 50 or status_st == "error" else "warning",
        "details": details,
        "error": err_str
    })

    # -------------------------------------------------------------
    # Stage 5: Reciprocal Rank Fusion (RRF) Calculation
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    rss_before, _ = _get_process_memory()
    status_st = "ok"
    err_str = None
    fused_hits = []
    details = {}
    try:
        from app.rag.services.rag_retriever import reciprocal_rank_fusion
        fused_hits = reciprocal_rank_fusion(dense_hits or [], sparse_hits or [])
        details = {"fused_count": len(fused_hits)}
    except Exception as e:
        status_st = "error"
        err_str = str(e)
    t_dur = round((time.perf_counter() - t0) * 1000, 2)
    c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
    rss_after, _ = _get_process_memory()
    raw_stage_records.append({
        "stage": "rrf_fusion_calculation",
        "duration_ms": t_dur,
        "cpu_time_ms": c_dur,
        "memory_rss_mb": rss_after,
        "memory_delta_mb": round(rss_after - rss_before, 2),
        "status": status_st,
        "details": details,
        "error": err_str
    })

    # -------------------------------------------------------------
    # Stage 6: Cross-Encoder Reranker (PyTorch CPU Inference)
    # -------------------------------------------------------------
    if include_reranker_test and fused_hits:
        t0 = time.perf_counter()
        cpu_t0 = time.process_time()
        rss_before, _ = _get_process_memory()
        status_st = "ok"
        err_str = None
        details = {}
        try:
            from app.rag.services.factory import AdapterFactory
            reranker = AdapterFactory.get_reranker()
            test_candidates = fused_hits[:5]
            _ = await asyncio.to_thread(reranker.rerank, query, test_candidates, top_n=len(test_candidates))
            details = {
                "model": getattr(reranker, "model_name", "BAAI/bge-reranker-base"),
                "evaluated_candidates": len(test_candidates),
            }
        except Exception as e:
            status_st = "error"
            err_str = str(e)
        t_dur = round((time.perf_counter() - t0) * 1000, 2)
        c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
        rss_after, _ = _get_process_memory()
        details["is_cpu_heavy"] = t_dur > 2000
        raw_stage_records.append({
            "stage": "cross_encoder_reranker_cpu",
            "duration_ms": t_dur,
            "cpu_time_ms": c_dur,
            "memory_rss_mb": rss_after,
            "memory_delta_mb": round(rss_after - rss_before, 2),
            "status": "ok" if t_dur < 500 else ("warning" if t_dur < 2000 else "error"),
            "details": details,
            "error": err_str
        })
        if t_dur > 2000:
            recommendations.append(
                f"⚠️ CPU Cross-Encoder Reranker consumed {t_dur/1000:.2f}s wall-clock and {c_dur/1000:.2f}s CPU compute time. "
                "Disabling reranker and adopting Pure RRF Hybrid Search (PGVector + BM25) will reduce chat latency by 80-95%."
            )
    else:
        rss_curr, _ = _get_process_memory()
        raw_stage_records.append({
            "stage": "cross_encoder_reranker_cpu",
            "duration_ms": 0.0,
            "cpu_time_ms": 0.0,
            "memory_rss_mb": rss_curr,
            "memory_delta_mb": 0.0,
            "status": "skipped",
            "details": {"reason": "include_reranker_test=False or no candidates"},
            "error": None
        })

    # -------------------------------------------------------------
    # Stage 7: S3 / MinIO Storage Connectivity Latency
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    rss_before, _ = _get_process_memory()
    status_st = "ok"
    err_str = None
    details = {}
    try:
        from app.services.storage import _get_client, _images_bucket
        s3 = _get_client()
        bucket = _images_bucket()
        if s3:
            await asyncio.to_thread(s3.head_bucket, Bucket=bucket)
            details = {"bucket": bucket}
        else:
            status_st = "warning"
            err_str = "S3 client is in local fallback mode"
    except Exception as e:
        status_st = "warning"
        err_str = str(e)
    t_dur = round((time.perf_counter() - t0) * 1000, 2)
    c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
    rss_after, _ = _get_process_memory()
    raw_stage_records.append({
        "stage": "s3_minio_storage_ping",
        "duration_ms": t_dur,
        "cpu_time_ms": c_dur,
        "memory_rss_mb": rss_after,
        "memory_delta_mb": round(rss_after - rss_before, 2),
        "status": status_st if t_dur < 500 or status_st == "warning" else "warning",
        "details": details,
        "error": err_str
    })

    # -------------------------------------------------------------
    # Stage 8: LLM API Roundtrip (Active Provider)
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    cpu_t0 = time.process_time()
    rss_before, _ = _get_process_memory()
    status_st = "ok"
    err_str = None
    details = {}
    try:
        from app.rag.services.factory import AdapterFactory
        llm_adapter = await AdapterFactory.get_dynamic_llm(db)
        test_prompt = f"Jawab dalam 1 kalimat pendek dan faktual: {query}"
        llm_response = await asyncio.to_thread(llm_adapter.generate, test_prompt)
        details = {
            "preview": (llm_response or "")[:100],
        }
    except Exception as e:
        status_st = "error"
        err_str = str(e)
    t_dur = round((time.perf_counter() - t0) * 1000, 2)
    c_dur = round((time.process_time() - cpu_t0) * 1000, 2)
    rss_after, _ = _get_process_memory()
    details["duration_sec"] = round(t_dur / 1000, 2)
    raw_stage_records.append({
        "stage": "llm_api_roundtrip_generation",
        "duration_ms": t_dur,
        "cpu_time_ms": c_dur,
        "memory_rss_mb": rss_after,
        "memory_delta_mb": round(rss_after - rss_before, 2),
        "status": status_st if t_dur < 3000 or status_st == "error" else "warning",
        "details": details,
        "error": err_str
    })
    if t_dur > 5000:
        recommendations.append(
            f"⚠️ LLM API call took {t_dur/1000:.2f}s. Check network connectivity between your AWS EC2 region (Jakarta) and the LLM API provider."
        )

    # -------------------------------------------------------------
    # Overall Bottleneck & Resource Intensity Calculation
    # -------------------------------------------------------------
    total_elapsed_ms = round((time.perf_counter() - t_start_total) * 1000, 2)

    # Build finalized StageLatencyMetric list with % share and CPU utilization %
    stages: List[StageLatencyMetric] = []
    for r in raw_stage_records:
        dur = r["duration_ms"]
        c_dur = r["cpu_time_ms"]
        share_pct = round((dur / max(total_elapsed_ms, 1)) * 100, 1)
        cpu_util = round((c_dur / max(dur, 0.001)) * 100, 1)
        stages.append(StageLatencyMetric(
            stage=r["stage"],
            duration_ms=dur,
            percentage_of_total=f"{share_pct}%",
            cpu_time_ms=c_dur,
            cpu_utilization_percent=f"{cpu_util}%",
            memory_rss_mb=r["memory_rss_mb"],
            memory_delta_mb=r["memory_delta_mb"],
            status=r["status"],
            details=r["details"],
            error=r["error"]
        ))

    # Identify primary resource stress stages
    active_stages = [s for s in stages if s.status != "skipped"]
    slowest_st = max(active_stages, key=lambda s: s.duration_ms) if active_stages else stages[0]
    most_cpu_st = max(active_stages, key=lambda s: s.cpu_time_ms) if active_stages else stages[0]
    most_mem_st = max(active_stages, key=lambda s: s.memory_delta_mb) if active_stages else stages[0]

    # Container Cgroup & Host Memory limits
    cgroup_info = _get_container_cgroup_info()
    c_lim_gb = cgroup_info.memory_limit_gb if cgroup_info.is_cgroup_limited else None
    c_used_gb = cgroup_info.memory_usage_gb if cgroup_info.is_cgroup_limited else None
    c_headroom = round(c_lim_gb - c_used_gb, 2) if (c_lim_gb and c_used_gb) else None

    resource_intensity = ResourceIntensitySummary(
        slowest_stage_name=slowest_st.stage,
        slowest_stage_duration_ms=slowest_st.duration_ms,
        slowest_stage_share=slowest_st.percentage_of_total,
        most_cpu_intensive_stage=f"{most_cpu_st.stage} ({most_cpu_st.cpu_time_ms} ms CPU time)",
        most_memory_intensive_stage=f"{most_mem_st.stage} ({most_mem_st.memory_delta_mb:+g} MB RAM)",
        container_ram_limit_gb=c_lim_gb,
        container_ram_used_gb=c_used_gb,
        container_ram_headroom_gb=c_headroom
    )

    # Determine primary bottleneck label
    if slowest_st.stage == "cross_encoder_reranker_cpu" and slowest_st.duration_ms > 1500:
        primary_bottleneck = "CROSS_ENCODER_RERANKER_CPU_BOUND"
    elif slowest_st.stage == "llm_api_roundtrip_generation" and slowest_st.duration_ms > 3000:
        primary_bottleneck = "LLM_NETWORK_LATENCY"
    elif slowest_st.stage == "dense_embedding_generation" and slowest_st.duration_ms > 1000:
        primary_bottleneck = "EMBEDDING_API_LATENCY"
    elif slowest_st.stage == "pgvector_similarity_search" and slowest_st.duration_ms > 500:
        primary_bottleneck = "VECTOR_DATABASE_QUERY_BOUND"
    else:
        primary_bottleneck = f"HIGHEST_LATENCY_IN_{slowest_st.stage.upper()}"

    gpu_info = _get_gpu_info()
    ram_info = _get_memory_info()
    logical_cores = os.cpu_count() or 1
    l1, _, _ = _get_load_averages()

    system_summary = {
        "cpu_cores": logical_cores,
        "load_average_1m": l1,
        "ram_total_gb": ram_info.total_gb,
        "ram_used_percent": ram_info.used_percent,
        "cuda_gpu_available": gpu_info.cuda_available,
        "running_on_cpu_only": not gpu_info.cuda_available,
    }

    if not gpu_info.cuda_available:
        recommendations.append(
            "ℹ️ Server is running on CPU without GPU acceleration. Avoid heavy PyTorch inference (like CrossEncoder) in request-response paths."
        )

    if c_headroom is not None and c_headroom < 0.8:
        recommendations.append(
            f"⚠️ Container RAM Headroom is low ({c_headroom} GB remaining of {c_lim_gb} GB limit). Consider increasing container memory limit to 6-8 GB."
        )

    if not recommendations:
        recommendations.append("✅ All system and RAG pipeline components responded within normal operating thresholds.")

    return EndToEndPerformanceResponse(
        status="success",
        timestamp=datetime.now(timezone.utc),
        test_query=query,
        total_elapsed_ms=total_elapsed_ms,
        primary_bottleneck=primary_bottleneck,
        resource_intensity=resource_intensity,
        system_summary=system_summary,
        stages=stages,
        recommendations=recommendations
    )


@router.get("/infrastructure-check", response_model=InfrastructureDiagnosticResponse, status_code=status.HTTP_200_OK)
async def run_infrastructure_check(request: Request) -> InfrastructureDiagnosticResponse:
    """
    Comprehensive Non-AI Infrastructure Diagnostic:
    - Event Loop Lag & CPU-blocking check
    - Database Connection Pool capacity & concurrent checkout latency (5 connections)
    - Egress DNS lookup, TLS handshake, and TTFB latencies to external cloud endpoints (OpenAI, Gemini, AWS S3)
    - Request Proxy Inspection (HTTP protocol version, Reverse Proxy headers)
    - Active Python threads count
    """
    findings: List[str] = []

    # 1. Event Loop Lag Check
    t_el0 = time.perf_counter()
    await asyncio.sleep(0)
    el_lag_ms = round((time.perf_counter() - t_el0) * 1000, 2)
    el_status = "ok" if el_lag_ms < 5 else ("warning" if el_lag_ms < 30 else "critical")
    if el_status != "ok":
        findings.append(
            f"⚠️ AsyncIO Event Loop has {el_lag_ms}ms scheduling lag. A CPU-bound task might be synchronously blocking the loop."
        )
    event_loop_res = EventLoopHealth(
        is_responsive=el_lag_ms < 100,
        lag_ms=el_lag_ms,
        status=el_status
    )

    # 2. Database Connection Pool Health
    pool = core_db_engine.pool
    p_size = pool.size()
    p_checkedin = pool.checkedin()
    p_checkedout = pool.checkedout()
    p_overflow = pool.overflow()

    t_db0 = time.perf_counter()
    try:
        async def ping_conn():
            async with AsyncSessionLocal() as session:
                res = await session.execute(text("SELECT 1"))
                res.scalar()
        await asyncio.gather(*[ping_conn() for _ in range(5)])
        conc_checkout_ms = round((time.perf_counter() - t_db0) * 1000, 2)
        db_status = "ok" if conc_checkout_ms < 50 else ("warning" if conc_checkout_ms < 250 else "critical")
    except Exception as e:
        conc_checkout_ms = round((time.perf_counter() - t_db0) * 1000, 2)
        db_status = "critical"
        findings.append(f"❌ Database connection checkout failed: {e}")

    if conc_checkout_ms > 200 and db_status != "critical":
        findings.append(f"⚠️ Concurrent DB connection checkout took {conc_checkout_ms}ms for 5 connections. Check PostgreSQL connection limits.")

    db_pool_res = DbPoolHealth(
        pool_size=p_size,
        checked_in=p_checkedin,
        checked_out=p_checkedout,
        overflow=p_overflow,
        concurrent_checkout_5_conns_ms=conc_checkout_ms,
        status=db_status
    )

    # 3. Egress Network & DNS Targets
    targets_to_test = [
        ("OpenAI API", "api.openai.com", "https://api.openai.com/v1/models"),
        ("Google Gemini API", "generativelanguage.googleapis.com", "https://generativelanguage.googleapis.com"),
        ("AWS S3 Jakarta", "skin-clinic-chatbot-dev.s3.ap-southeast-3.amazonaws.com", "https://skin-clinic-chatbot-dev.s3.ap-southeast-3.amazonaws.com"),
    ]
    egress_results: List[EgressNetworkTarget] = []

    for name, host, url in targets_to_test:
        dns_ms = 0.0
        ttfb_ms = 0.0
        tcp_tls_ms = 0.0
        status_code = None
        target_status = "ok"
        err_msg = None

        # DNS Resolution test
        t_dns0 = time.perf_counter()
        try:
            _ = await asyncio.to_thread(socket.getaddrinfo, host, 443)
            dns_ms = round((time.perf_counter() - t_dns0) * 1000, 2)
        except Exception as e:
            dns_ms = round((time.perf_counter() - t_dns0) * 1000, 2)
            target_status = "error"
            err_msg = f"DNS failed: {e}"

        # HTTP/TLS TTFB test
        if target_status != "error":
            t_net0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=4.0, verify=True) as client:
                    resp = await client.head(url)
                    status_code = resp.status_code
                ttfb_ms = round((time.perf_counter() - t_net0) * 1000, 2)
                tcp_tls_ms = max(0.0, round(ttfb_ms - dns_ms, 2))
                if ttfb_ms > 1000:
                    target_status = "warning"
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                ttfb_ms = round((time.perf_counter() - t_net0) * 1000, 2)
                tcp_tls_ms = max(0.0, round(ttfb_ms - dns_ms, 2))
            except Exception as e:
                ttfb_ms = round((time.perf_counter() - t_net0) * 1000, 2)
                target_status = "error"
                err_msg = f"Network/TLS error: {e}"

        if ttfb_ms > 1500:
            findings.append(f"⚠️ Egress latency to {name} ({host}) is high ({ttfb_ms}ms TTFB). Check server outbound internet connection.")

        egress_results.append(EgressNetworkTarget(
            target=f"{name} ({host})",
            dns_lookup_ms=dns_ms,
            tcp_tls_handshake_ms=tcp_tls_ms,
            ttfb_ms=ttfb_ms,
            status_code=status_code,
            status=target_status,
            error=err_msg
        ))

    # 4. Request & Reverse Proxy Inspection
    http_ver = request.scope.get("http_version", "1.1")
    proxy_headers: Dict[str, str] = {}
    for h in ("x-forwarded-for", "x-forwarded-proto", "x-real-ip", "via", "server", "cf-ray", "x-forwarded-host"):
        val = request.headers.get(h)
        if val:
            proxy_headers[h] = val

    client_ip = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    is_proxy = bool(proxy_headers)

    if http_ver == "1.1":
        findings.append(
            "ℹ️ Incoming request is using HTTP/1.1. In production, enable HTTP/2 or HTTP/3 on your Reverse Proxy (Nginx/Cloudflare) for full connection multiplexing."
        )

    proxy_info = RequestProxyInspection(
        http_version=f"HTTP/{http_ver}",
        client_ip=client_ip,
        is_behind_reverse_proxy=is_proxy,
        proxy_headers_detected=proxy_headers
    )

    if not findings:
        findings.append("✅ All non-AI infrastructure components (Event Loop, DB Pool, Egress DNS & Network) are healthy.")

    return InfrastructureDiagnosticResponse(
        status="success",
        timestamp=datetime.now(timezone.utc),
        event_loop=event_loop_res,
        database_pool=db_pool_res,
        egress_network=egress_results,
        request_proxy=proxy_info,
        active_threads=threading.active_count(),
        diagnosis=findings
    )


@router.get("/sse-buffering-test", summary="Test live SSE streaming chunk delivery against proxy buffering")
async def sse_buffering_test():
    """
    Live Server-Sent Events (SSE) Proxy Buffering Verification Endpoint:
    - Yields 5 incremental chunks with 400ms delay.
    - If Nginx / Cloudflare proxy buffering is OFF: Chunks appear in real-time one by one every 400ms.
    - If proxy buffering is ON: Client experiences a 2-second freeze, then all chunks arrive simultaneously.
    """
    async def event_generator():
        import json
        for i in range(1, 6):
            chunk_data = {
                "step": i,
                "total_steps": 5,
                "message": f"Streaming chunk {i}/5 received successfully",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"
            await asyncio.sleep(0.4)
        yield "data: [DONE]\n\n"

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Nginx directive to disable response buffering
    }
    return StreamingResponse(event_generator(), headers=headers, media_type="text/event-stream")

