import base64
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.database import get_db
from app.core.broadcaster import broadcaster
from app.services.cis_sync import (
    get_cis_public_key,
    upsert_branch_payload,
    delete_branch_payload,
    upsert_doctor_payload,
    delete_doctor_payload,
    upsert_user_branch_payload,
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
    event: str # "branch.upsert", "branch.delete", "user.upsert", "user.delete", "user_branch.upsert", "bulk.sync"
    data: Any # Can be dict or list depending on event

@router.post("/cis", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_rsa_signature)])
async def handle_cis_webhook(
    payload: WebhookEventPayload,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive RSA-signed data pushes from CIS.
    """
    try:
        summary: Dict[str, Any] = {}
        event_name = (payload.event or "").strip().lower()

        if event_name in ("branch.upsert", "branch.create", "branch.update"):
            res = await upsert_branch_payload(db, payload.data)
            count = len(res) if isinstance(res, list) else 1
            summary = {"branches_upserted": count}
        elif event_name in ("branch.delete", "branch.remove"):
            data = payload.data
            if isinstance(data, list):
                for item in data:
                    await delete_branch_payload(db, item)
                summary = {"branches_deleted": len(data)}
            else:
                await delete_branch_payload(db, data)
                summary = {"branches_deleted": 1}
        elif event_name in ("user.upsert", "user.create", "user.update", "doctor.upsert", "doctor.create", "doctor.update"):
            res = await upsert_doctor_payload(db, payload.data)
            count = len(res) if isinstance(res, list) else 1
            summary = {"doctors_upserted": count}
        elif event_name in ("user.delete", "user.remove", "doctor.delete", "doctor.remove"):
            data = payload.data
            if isinstance(data, list):
                for item in data:
                    await delete_doctor_payload(db, item)
                summary = {"doctors_deleted": len(data)}
            else:
                await delete_doctor_payload(db, data)
                summary = {"doctors_deleted": 1}
        elif event_name in ("user_branch.upsert", "user_branch.create", "user_branch.update", "doctor_branch.upsert"):
            data_list = payload.data if isinstance(payload.data, list) else [payload.data]
            await upsert_user_branch_payload(db, data_list)
            summary = {"mappings_upserted": len(data_list)}
        elif event_name == "bulk.sync":
            summary = await bulk_sync_payload(db, payload.data)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported event type: {payload.event}")

        await db.commit()
        await broadcaster.publish("sync_completed")
        logger.info(f"Successfully processed CIS webhook event '{payload.event}': {summary}")
        return {"status": "success", "event": payload.event, "summary": summary}
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed processing CIS webhook event '{payload.event}': {e}")
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")
