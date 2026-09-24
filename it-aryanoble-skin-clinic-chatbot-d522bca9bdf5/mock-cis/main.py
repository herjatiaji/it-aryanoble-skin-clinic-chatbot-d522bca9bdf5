import os
import json
import base64
import asyncio
import logging
import httpx
# pyrefly: ignore [missing-import]
import jwt
import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger("mock-cis")
logging.basicConfig(level=logging.INFO)

KEYS_DIR = os.path.join(os.path.dirname(__file__), "keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private_key.pem")

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
BACKEND_WEBHOOK_URL = os.getenv("BACKEND_WEBHOOK_URL", f"{BACKEND_URL}/api/webhooks/cis")

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

def sign_proxy_payload(body_bytes: bytes, user_id: str) -> str:
    private_key = load_private_key()
    payload_to_sign = user_id.encode("utf-8") + b":" + body_bytes
    signature = private_key.sign(
        payload_to_sign,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")

# Mock Master Data
MOCK_BRANCHES = [
    {
        "id": 838,
        "name": "Klinik Utama Erha Ultimate BSD",
        "code": "011",
        "ecosystem": "Erha",
        "status": "1"
    },
    {
            "id": 839,
            "name": "Klinik Utama Erha Ultimate TRG",
            "code": "012",
            "ecosystem": "Erha",
            "status": "1"
        },
    {
        "id": 847,
        "name": "Klinik Utama Dermies BSD",
        "code": "034",
        "ecosystem": "Dermies",
        "status": "1"
    }
]

MOCK_DOCTORS = [
    {
        "id": 1,
        "name": "dr Sulistyo SpKK",
        "user_type": "1",
        "user_type_name": "Doctor SpKK",
        "nik": "dr00123",
        "email": "drkk11@gmail.com",
        "ecosystem": "Erha",
        "status": "1",
        "user_branchs": [
            {
                "branch_id": 838,
                "branch_code": "011",
                "status": "1"
            },
            {
                "branch_id": 847,
                "branch_code": "034",
                "status": "0"
            }
        ]
    },
    {
        "id": 2,
        "name": "dr Budi Santoso",
        "user_type": "173",
        "user_type_name": "Doctor gp",
        "nik": "dr00456",
        "email": "drbudi@gmail.com",
        "ecosystem": "Dermies",
        "status": "1",
        "user_branchs": [
            {
                "branch_id": 847,
                "branch_code": "034",
                "status": "1"
            }
        ]
    },
    {
        "id": 3,
        "name": "dr Clarissa SpDV",
        "user_type": "1",
        "user_type_name": "Doctor SpKK",
        "nik": "dr00789",
        "email": "drclarissa@gmail.com",
        "ecosystem": "Erha",
        "status": "1",
        "user_branchs": [
            {
                "branch_id": 839,
                "branch_code": "012",
                "status": "1"
            }
        ]
    }
]

MOCK_USER_BRANCHES = [
    {
        "user_id": 1,
        "branch_id": 838,
        "branch_code": "011",
        "status": "1",
        "ecosystem": "Erha"
    },
    {
        "user_id": 2,
        "branch_id": 847,
        "branch_code": "034",
        "status": "1",
        "ecosystem": "Dermies"
    },
    {
        "user_id": 3,
        "branch_id": 839,
        "branch_code": "012",
        "status": "1",
        "ecosystem": "Erha"
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
            "users": MOCK_DOCTORS,
            "user_branches": MOCK_USER_BRANCHES
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
    cis_id: Any

@app.post("/api/login")
async def login(req: LoginRequest):
    doctor = next((d for d in MOCK_DOCTORS if str(d.get("id")) == str(req.cis_id) or str(d.get("cis_id")) == str(req.cis_id)), None)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    private_key = load_private_key()
    user_id = str(doctor.get("id") or doctor.get("cis_id"))
    payload = {
        "sub": user_id,
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
        "event": "user.upsert",
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

@app.post("/trigger/push-user-branch")
async def trigger_push_user_branch(webhook_url: Optional[str] = None):
    payload = {
        "event": "user_branch.upsert",
        "data": MOCK_USER_BRANCHES
    }
    return await send_signed_webhook(payload, webhook_url)

@app.post("/trigger/push-all")
async def trigger_push_all(webhook_url: Optional[str] = None):
    payload = {
        "event": "bulk.sync",
        "data": {
            "branches": MOCK_BRANCHES,
            "users": MOCK_DOCTORS,
            "user_branches": MOCK_USER_BRANCHES
        }
    }
    return await send_signed_webhook(payload, webhook_url)

async def forward_to_backend(request: Request, method: str, path: str):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    body_bytes = await request.body()
    signature = sign_proxy_payload(body_bytes, str(user_id))

    target_url = f"{BACKEND_URL}{path}"
    
    headers = {
        "X-Signature": signature,
        "X-User-Id": str(user_id),
        "Content-Type": request.headers.get("content-type") or "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, target_url, content=body_bytes, headers=headers)
            from fastapi.responses import Response
            # Filter out hop-by-hop headers and transfer-encoding before returning
            filtered_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ["transfer-encoding", "content-length"]}
            return Response(content=resp.content, status_code=resp.status_code, headers=filtered_headers)
    except httpx.RequestError as e:
        logger.error(f"Error forwarding request to backend ({target_url}): {e}")
        raise HTTPException(status_code=502, detail=f"Backend connection error: {str(e)}")

async def stream_to_backend(request: Request, path: str):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    body_bytes = await request.body()
    signature = sign_proxy_payload(body_bytes, str(user_id))

    target_url = f"{BACKEND_URL}{path}"
    
    headers = {
        "X-Signature": signature,
        "X-User-Id": str(user_id),
        "Content-Type": request.headers.get("content-type") or "application/json"
    }

    client = httpx.AsyncClient(timeout=300.0)
    
    async def sse_generator():
        try:
            async with client.stream("POST", target_url, content=body_bytes, headers=headers) as response:
                if response.status_code not in (200, 201):
                    err_body = await response.aread()
                    yield f"data: {json.dumps({'error': 'Backend error', 'status': response.status_code, 'detail': err_body.decode('utf-8')})}\n\n"
                    return
                async for chunk in response.aiter_raw():
                    yield chunk
        except httpx.RequestError as e:
            yield f"data: {json.dumps({'error': 'Backend connection error', 'detail': str(e)})}\n\n"
        finally:
            await client.aclose()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive"
        }
    )

@app.get("/api/chats/")
async def proxy_get_chats(request: Request):
    return await forward_to_backend(request, "GET", "/api/chats/")

@app.post("/api/chats/")
async def proxy_post_chats(request: Request):
    return await forward_to_backend(request, "POST", "/api/chats/")

@app.put("/api/chats/{session_id}")
async def proxy_put_chat(session_id: str, request: Request):
    return await forward_to_backend(request, "PUT", f"/api/chats/{session_id}")

@app.get("/api/chats/{session_id}/messages")
async def proxy_get_chat_messages(session_id: str, request: Request):
    return await forward_to_backend(request, "GET", f"/api/chats/{session_id}/messages")

@app.post("/api/chats/{session_id}/messages")
async def proxy_chat_messages(session_id: str, request: Request):
    return await stream_to_backend(request, f"/api/chats/{session_id}/messages")

@app.post("/api/chats/{session_id}/messages/stream")
async def proxy_chat_stream(session_id: str, request: Request):
    return await stream_to_backend(request, f"/api/chats/{session_id}/messages/stream")

@app.get("/api/storage/{s3_key:path}")
async def proxy_storage_asset(s3_key: str, request: Request):
    clean_key = s3_key.lstrip("/")
    target_url = f"{BACKEND_URL}/api/storage/{clean_key}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(target_url)
            filtered_headers = {
                k: v for k, v in resp.headers.items() 
                if k.lower() not in ["transfer-encoding", "content-length"]
            }
            return Response(content=resp.content, status_code=resp.status_code, headers=filtered_headers)
    except httpx.RequestError as e:
        logger.error(f"Error proxying storage asset ({target_url}): {e}")
        raise HTTPException(status_code=502, detail=f"Backend storage connection error: {str(e)}")

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
