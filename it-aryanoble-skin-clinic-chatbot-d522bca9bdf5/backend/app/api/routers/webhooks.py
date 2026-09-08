import base64
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.database import get_db
from app.services.cis_sync import (
    get_cis_public_key,
    upsert_branch_payload,
    delete_branch_payload,
    upsert_doctor_payload,
    delete_doctor_payload,
    bulk_sync_payload
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

async def verify_rsa_signature(request: Request, x_signature: Optional[str] = Header(None, alias="X-Signature")):
    """Dependency verifying RSA signature on raw HTTP request body against X-Signature header."""
    if not x_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Signature header"
        )
        
    body_bytes = await request.body()
    try:
        signature_bytes = base64.b64decode(x_signature)
        public_key = get_cis_public_key()
        public_key.verify(
            signature_bytes,
            body_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
    except Exception as e:
        logger.error(f"RSA signature verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid RSA signature"
        )
    return True

class WebhookEventPayload(BaseModel):
    event: str # "branch.upsert", "branch.delete", "doctor.upsert", "doctor.delete", "bulk.sync"
    data: Dict[str, Any]

@router.post("/cis", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_rsa_signature)])
async def handle_cis_webhook(
    payload: WebhookEventPayload,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive RSA-signed data pushes from CIS.
    """
    try:
        if payload.event == "branch.upsert":
            await upsert_branch_payload(db, payload.data)
        elif payload.event == "branch.delete":
            branch_id = payload.data.get("id") or payload.data.get("branch_id")
            if branch_id:
                await delete_branch_payload(db, branch_id)
        elif payload.event == "doctor.upsert":
            await upsert_doctor_payload(db, payload.data)
        elif payload.event == "doctor.delete":
            cis_id = payload.data.get("cis_id") or payload.data.get("doctor_cis_id")
            if cis_id:
                await delete_doctor_payload(db, cis_id)
        elif payload.event == "bulk.sync":
            await bulk_sync_payload(db, payload.data)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported event type: {payload.event}")

        await db.commit()
        return {"status": "success", "event": payload.event}
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed processing CIS webhook event '{payload.event}': {e}")
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")
