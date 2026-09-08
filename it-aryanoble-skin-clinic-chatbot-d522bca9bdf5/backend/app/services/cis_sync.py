import os
import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cryptography.hazmat.primitives import serialization

from app.models.user import User, UserType
from app.models.branch import Branch, UserBranch
from app.core.config import settings

logger = logging.getLogger(__name__)

def get_cis_public_key():
    """Load RSA Public Key supporting PEM (PKCS#1 / PKCS#8) and OpenSSH (ssh-rsa) formats."""
    if settings.CIS_RSA_PUBLIC_KEY:
        raw_key = settings.CIS_RSA_PUBLIC_KEY.replace("\\n", "\n")
        key_bytes = raw_key.encode("utf-8")
    elif settings.CIS_RSA_PUBLIC_KEY_PATH:
        path = settings.CIS_RSA_PUBLIC_KEY_PATH
        if not os.path.isabs(path):
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            path = os.path.join(base_dir, path)
            
        if not os.path.exists(path):
            raise RuntimeError(f"CIS RSA Public Key file not found at: {path}")
            
        with open(path, "rb") as f:
            key_bytes = f.read()
    else:
        raise RuntimeError("CIS RSA Public Key is not configured in environment variables (CIS_RSA_PUBLIC_KEY or CIS_RSA_PUBLIC_KEY_PATH).")

    key_str = key_bytes.decode("utf-8", errors="ignore").strip()
    if key_str.startswith("ssh-rsa"):
        return serialization.load_ssh_public_key(key_bytes)
    return serialization.load_pem_public_key(key_bytes)

async def upsert_branch_payload(db: AsyncSession, data: Dict[str, Any]) -> Branch:
    """Upsert a branch record from pushed webhook data payload."""
    b_id_str = data.get("id") or data.get("branch_id")
    if not b_id_str:
        raise ValueError("Missing branch id in payload")
    
    b_id = uuid.UUID(b_id_str)
    name = data.get("name")
    address = data.get("address")
    image_url = data.get("image_url")
    
    stmt = select(Branch).where(Branch.id == b_id)
    branch = (await db.execute(stmt)).scalar_one_or_none()
    
    if not branch:
        branch = Branch(
            id=b_id,
            name=name,
            address=address,
            image_url=image_url
        )
        db.add(branch)
    else:
        branch.name = name
        branch.address = address
        branch.image_url = image_url
        branch.deleted_at = None
        
    await db.flush()
    return branch

async def delete_branch_payload(db: AsyncSession, branch_id: str):
    """Soft delete a branch record."""
    b_id = uuid.UUID(branch_id)
    stmt = select(Branch).where(Branch.id == b_id)
    branch = (await db.execute(stmt)).scalar_one_or_none()
    if branch:
        branch.deleted_at = datetime.now(timezone.utc)
        await db.flush()

async def upsert_doctor_payload(db: AsyncSession, data: Dict[str, Any]) -> User:
    """Upsert a doctor record and branch associations from pushed webhook payload."""
    cis_id = data.get("cis_id") or data.get("doctor_cis_id")
    if not cis_id:
        raise ValueError("Missing doctor cis_id in payload")
        
    name = data.get("name")
    email = data.get("email")
    employee_id = data.get("employee_id")
    dr_type = data.get("dr_type")
    ecosystem = data.get("ecosystem", "ERHA")
    branch_ids = data.get("branch_ids", [])
    status = data.get("status")
    
    stmt = select(User).where(User.cis_id == cis_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    is_inactive = (status and status.lower() == "inactive")
    
    if not user:
        user = User(
            email=email,
            name=name,
            cis_id=cis_id,
            employee_id=employee_id,
            dr_type=dr_type,
            ecosystem=ecosystem,
            type=UserType.DOCTOR,
            token_limit=0
        )
        if is_inactive:
            user.deleted_at = datetime.now(timezone.utc)
        db.add(user)
    else:
        user.name = name
        user.email = email
        user.employee_id = employee_id
        user.dr_type = dr_type
        user.ecosystem = ecosystem
        if is_inactive:
            user.deleted_at = datetime.now(timezone.utc)
        else:
            user.deleted_at = None
        
    await db.flush()
    
    # Sync Doctor-Branch associations
    # Remove existing branch mappings for this user
    await db.execute(UserBranch.__table__.delete().where(UserBranch.user_id == user.id))
    
    # Re-add mappings if branch exists
    for b_id_str in branch_ids:
        b_id = uuid.UUID(b_id_str)
        b_stmt = select(Branch).where(Branch.id == b_id)
        branch = (await db.execute(b_stmt)).scalar_one_or_none()
        if branch:
            db.add(UserBranch(user_id=user.id, branch_id=b_id))
            
    await db.flush()
    return user

async def delete_doctor_payload(db: AsyncSession, cis_id: str):
    """Soft delete a doctor record."""
    stmt = select(User).where(User.cis_id == cis_id, User.type == UserType.DOCTOR)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user:
        user.deleted_at = datetime.now(timezone.utc)
        await db.flush()

async def bulk_sync_payload(db: AsyncSession, data: Dict[str, Any]):
    """Process a full bulk sync payload containing branches and doctors lists."""
    branches_data = data.get("branches", [])
    doctors_data = data.get("doctors", [])
    
    pulled_branch_ids = set()
    for b_data in branches_data:
        branch = await upsert_branch_payload(db, b_data)
        pulled_branch_ids.add(branch.id)
        
    # Soft delete local branches omitted from full sync
    all_b_stmt = select(Branch).where(Branch.deleted_at.is_(None))
    all_branches = (await db.execute(all_b_stmt)).scalars().all()
    for b in all_branches:
        if b.id not in pulled_branch_ids:
            b.deleted_at = datetime.now(timezone.utc)
            
    pulled_doc_cis_ids = set()
    for d_data in doctors_data:
        doctor = await upsert_doctor_payload(db, d_data)
        pulled_doc_cis_ids.add(doctor.cis_id)
        
    # Soft delete local doctors omitted from full sync
    all_d_stmt = select(User).where(User.type == UserType.DOCTOR, User.deleted_at.is_(None))
    all_doctors = (await db.execute(all_d_stmt)).scalars().all()
    for d in all_doctors:
        if d.cis_id and d.cis_id not in pulled_doc_cis_ids:
            d.deleted_at = datetime.now(timezone.utc)
            
    await db.flush()
