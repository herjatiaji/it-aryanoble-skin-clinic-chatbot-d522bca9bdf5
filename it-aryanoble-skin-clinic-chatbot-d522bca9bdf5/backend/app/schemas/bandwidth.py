from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class BandwidthTestResponse(BaseModel):
    status: str = Field(default="success", description="Status of the test")
    download: str = Field(..., description="Download speed formatted string (e.g. '84.32 Mbps')")
    upload: str = Field(..., description="Upload speed formatted string (e.g. '32.18 Mbps')")
    ping: str = Field(..., description="Ping latency formatted string (e.g. '14.5 ms')")
    download_mbps: float = Field(..., description="Download speed numeric value in Mbps")
    upload_mbps: float = Field(..., description="Upload speed numeric value in Mbps")
    ping_ms: float = Field(..., description="Ping latency numeric value in ms")
    isp: Optional[str] = Field(default="Unknown", description="Client Internet Service Provider")
    server: Optional[str] = Field(default="Unknown", description="Test server location and sponsor")
    client_ip: Optional[str] = Field(default=None, description="Public IP address")
    duration: Optional[str] = Field(default=None, description="Execution duration in seconds")
    timestamp: datetime = Field(description="UTC execution timestamp")
