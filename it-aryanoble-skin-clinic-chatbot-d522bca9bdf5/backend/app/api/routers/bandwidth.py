import asyncio
from datetime import datetime, timezone
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from loguru import logger

from app.schemas.bandwidth import BandwidthTestResponse

router = APIRouter(prefix="/bandwidth", tags=["Bandwidth Tracker"])


def _execute_speedtest_sync(server_id: Optional[int] = None) -> dict:
    """Executes speedtest-cli benchmark synchronously in a worker thread."""
    try:
        import speedtest
    except ImportError:
        raise RuntimeError("speedtest-cli is not installed. Run: pip install speedtest-cli")

    st = speedtest.Speedtest(secure=True)
    if server_id:
        st.get_servers([server_id])
    st.get_best_server()
    st.download(threads=None)
    st.upload(threads=None)
    return st.results.dict()


@router.get("/test", response_model=BandwidthTestResponse, status_code=status.HTTP_200_OK)
@router.post("/test", response_model=BandwidthTestResponse, status_code=status.HTTP_200_OK)
async def run_bandwidth_test(
    server_id: Optional[int] = Query(None, description="Optional Speedtest server ID"),
):
    """
    Runs a live speedtest using speedtest-cli and returns clean, humanized throughput metrics.
    """
    start_time = time.time()
    logger.info("Running speedtest benchmark...")

    try:
        results = await asyncio.to_thread(_execute_speedtest_sync, server_id)
    except Exception as exc:
        logger.error(f"Speedtest error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speedtest failed: {str(exc)}",
        )

    elapsed = round(time.time() - start_time, 2)
    server_data = results.get("server", {})
    client_data = results.get("client", {})

    download_mbps = round(results.get("download", 0.0) / 1_000_000, 2)
    upload_mbps = round(results.get("upload", 0.0) / 1_000_000, 2)
    ping_ms = round(results.get("ping", 0.0), 2)

    server_loc = f"{server_data.get('name', 'N/A')}, {server_data.get('country', '')}".strip(", ")
    sponsor = server_data.get("sponsor", "")
    server_text = f"{server_loc} ({sponsor})" if sponsor else server_loc
    isp_text = client_data.get("isp", "Unknown")

    return BandwidthTestResponse(
        status="success",
        download=f"{download_mbps} Mbps",
        upload=f"{upload_mbps} Mbps",
        ping=f"{ping_ms} ms",
        download_mbps=download_mbps,
        upload_mbps=upload_mbps,
        ping_ms=ping_ms,
        isp=isp_text,
        server=server_text,
        client_ip=client_data.get("ip"),
        duration=f"{elapsed}s",
        timestamp=datetime.now(timezone.utc),
    )
