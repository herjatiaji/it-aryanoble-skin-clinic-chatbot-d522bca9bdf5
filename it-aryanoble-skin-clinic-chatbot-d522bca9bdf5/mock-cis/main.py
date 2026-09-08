import os
import json
import base64
import asyncio
import httpx
import jwt
import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

KEYS_DIR = os.path.join(os.path.dirname(__file__), "keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private_key.pem")

BACKEND_WEBHOOK_URL = os.getenv("BACKEND_WEBHOOK_URL", "http://localhost:8000/api/webhooks/cis")

def load_private_key():
    if not os.path.exists(PRIVATE_KEY_PATH):
        raise RuntimeError(f"Private key not found at {PRIVATE_KEY_PATH}")
    with open(PRIVATE_KEY_PATH, "rb") as key_file:
        return serialization.load_pem_private_key(
            key_file.read(),
            password=None
        )

def sign_payload_bytes(payload_bytes: bytes) -> str:
    private_key = load_private_key()
    signature = private_key.sign(
        payload_bytes,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")

# Mock Master Data
MOCK_BRANCHES = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Jakarta Central Clinic",
        "address": "Sudirman St. No. 12, South Jakarta"
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "Bandung Main Clinic",
        "address": "Ir. H. Juanda St. (Dago) No. 45, Bandung"
    },
    {
        "id": "33333333-3333-3333-3333-333333333333",
        "name": "Surabaya Skin Care Center",
        "address": "Pemuda St. No. 88, Surabaya"
    },
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "name": "Bali Medical & Esthetics",
        "address": "Sunset Road No. 101, Seminyak, Bali"
    },
    {
        "id": "55555555-5555-5555-5555-555555555555",
        "name": "Yogyakarta Health & Wellness",
        "address": "Malioboro St. No. 15, Yogyakarta"
    }
]

MOCK_DOCTORS = [
    {
        "cis_id": "DR-12345",
        "employee_id": "EMP-001",
        "dr_type": "SpDVE",
        "ecosystem": "ERHA",
        "status": "active",
        "name": "Dr. Jane Doe, Sp.D.V.E.",
        "email": "doctor@mail.com",
        "branch_ids": [
            "11111111-1111-1111-1111-111111111111"
        ]
    },
    {
        "cis_id": "DR-67890",
        "employee_id": "EMP-002",
        "dr_type": "SpDVE",
        "ecosystem": "ERHA",
        "status": "active",
        "name": "Dr. John Smith, Sp.D.V.E.",
        "email": "john.smith@example.com",
        "branch_ids": [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222"
        ]
    },
    {
        "cis_id": "DR-11223",
        "employee_id": "EMP-003",
        "dr_type": "GP Plus",
        "ecosystem": "ERHA",
        "status": "active",
        "name": "Dr. Amanda Prasetya",
        "email": "amanda.prasetya@example.com",
        "branch_ids": [
            "22222222-2222-2222-2222-222222222222",
            "55555555-5555-5555-5555-555555555555"
        ]
    },
    {
        "cis_id": "DR-44556",
        "employee_id": "EMP-004",
        "dr_type": "GP Plus",
        "ecosystem": "ERHA",
        "status": "active",
        "name": "Dr. Budi Santoso, Sp.B.P.R.E.",
        "email": "budi.santoso@example.com",
        "branch_ids": [
            "33333333-3333-3333-3333-333333333333"
        ]
    },
    {
        "cis_id": "DR-77889",
        "employee_id": "EMP-005",
        "dr_type": "SpDVE",
        "ecosystem": "ERHA",
        "status": "active",
        "name": "Dr. Citra Dewi",
        "email": "citra.dewi@example.com",
        "branch_ids": [
            "11111111-1111-1111-1111-111111111111",
            "44444444-4444-4444-4444-444444444444"
        ]
    },
    {
        "cis_id": "DR-99001",
        "employee_id": "EMP-006",
        "dr_type": "GP Plus",
        "ecosystem": "ERHA",
        "status": "inactive",
        "name": "Dr. Edward Wijaya",
        "email": "edward.wijaya@example.com",
        "branch_ids": [
            "33333333-3333-3333-3333-333333333333",
            "44444444-4444-4444-4444-444444444444"
        ]
    }
]

import logging

logger = logging.getLogger("mock_cis")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

async def send_signed_webhook(event_payload: Dict[str, Any], webhook_url: Optional[str] = None):
    target_url = webhook_url or BACKEND_WEBHOOK_URL
    body_bytes = json.dumps(event_payload, separators=(',', ':')).encode("utf-8")
    signature = sign_payload_bytes(body_bytes)
    
    headers = {
        "Content-Type": "application/json",
        "X-Signature": signature
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(target_url, content=body_bytes, headers=headers)
        return {
            "status_code": resp.status_code,
            "response": resp.json() if resp.headers.get("content-type") == "application/json" else resp.text
        }

async def auto_sync_task():
    """Automatically push initial mock data on startup and repeat every 1 hour (3600s)."""
    payload = {
        "event": "bulk.sync",
        "data": {
            "branches": MOCK_BRANCHES,
            "doctors": MOCK_DOCTORS
        }
    }
    
    # 1. Initial push on startup (immediate attempt 1, with retries for startup timing)
    for attempt in range(1, 6):
        try:
            if attempt > 1:
                await asyncio.sleep(3)
                
            logger.info(f"Auto-pushing initial mock data to backend ({BACKEND_WEBHOOK_URL}) - Attempt {attempt}/5...")
            res = await send_signed_webhook(payload)
            logger.info(f"Auto-push response status: {res.get('status_code')} - {res.get('response')}")
            if res.get("status_code") in (200, 202):
                break
        except Exception as e:
            logger.error(f"Auto-push attempt {attempt} failed: {e}. Retrying in 3s...")

    # 2. Recurring periodic push (every 1 hour = 3600 seconds)
    while True:
        await asyncio.sleep(3600)
        try:
            logger.info(f"Running hourly scheduled push to backend ({BACKEND_WEBHOOK_URL})...")
            res = await send_signed_webhook(payload)
            logger.info(f"Hourly push status: {res.get('status_code')} - {res.get('response')}")
        except Exception as e:
            logger.error(f"Hourly scheduled push failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting mock-cis service and initializing auto_sync_task background worker...")
    task = asyncio.create_task(auto_sync_task())
    yield
    logger.info("Stopping mock-cis background worker...")
    task.cancel()

app = FastAPI(title="CIS Dashboard Mock API & Webhook Pusher", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/doctors")
async def get_doctors():
    return MOCK_DOCTORS

class LoginRequest(BaseModel):
    cis_id: str

@app.post("/api/login")
async def login(req: LoginRequest):
    doctor = next((d for d in MOCK_DOCTORS if d["cis_id"] == req.cis_id), None)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    private_key = load_private_key()
    payload = {
        "sub": doctor["cis_id"],
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=12)
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "doctor": doctor
    }

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-cis"}

@app.post("/trigger/push-doctor")
async def trigger_push_doctor(doctor_index: int = 0, webhook_url: Optional[str] = None):
    if doctor_index < 0 or doctor_index >= len(MOCK_DOCTORS):
        raise HTTPException(status_code=400, detail="Invalid doctor index")
    
    payload = {
        "event": "doctor.upsert",
        "data": MOCK_DOCTORS[doctor_index]
    }
    return await send_signed_webhook(payload, webhook_url)

@app.post("/trigger/push-branch")
async def trigger_push_branch(branch_index: int = 0, webhook_url: Optional[str] = None):
    if branch_index < 0 or branch_index >= len(MOCK_BRANCHES):
        raise HTTPException(status_code=400, detail="Invalid branch index")
    
    payload = {
        "event": "branch.upsert",
        "data": MOCK_BRANCHES[branch_index]
    }
    return await send_signed_webhook(payload, webhook_url)

@app.post("/trigger/push-all")
async def trigger_push_all(webhook_url: Optional[str] = None):
    payload = {
        "event": "bulk.sync",
        "data": {
            "branches": MOCK_BRANCHES,
            "doctors": MOCK_DOCTORS
        }
    }
    return await send_signed_webhook(payload, webhook_url)

# Serve static files from React build (dist folder)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("trigger/") or full_path == "health":
            raise HTTPException(status_code=404, detail="Endpoint not found")
            
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend build not found")
