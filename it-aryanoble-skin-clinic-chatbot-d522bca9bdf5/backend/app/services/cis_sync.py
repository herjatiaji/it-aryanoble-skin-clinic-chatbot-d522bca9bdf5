import os
import logging
import uuid
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
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

def parse_cis_int(raw_id: Any) -> Optional[int]:
    """
    Safely coerces CIS numeric identifiers into integers.
    Supports integer types, numeric strings with optional whitespace, and floats.
    Returns None if missing, empty, or non-numeric.
    """
    if raw_id is None:
        return None
    if isinstance(raw_id, (int, float)):
        try:
            return int(raw_id)
        except (ValueError, TypeError, OverflowError):
            return None
    raw_str = str(raw_id).strip()
    if not raw_str:
        return None
    try:
        return int(raw_str)
    except (ValueError, TypeError):
        try:
            f = float(raw_str)
            if f.is_integer():
                return int(f)
        except (ValueError, TypeError, OverflowError):
            pass
        return None

async def _upsert_single_branch(db: AsyncSession, data: Dict[str, Any]) -> Branch:
    """Upsert an individual branch record."""
    if not isinstance(data, dict):
        raise ValueError(f"Invalid branch data: expected dict, got {type(data).__name__}")
        
    raw_id = data.get("id") or data.get("branch_id")
    external_id = parse_cis_int(raw_id)
    if external_id is None:
        raise ValueError(f"Invalid or missing branch id in payload: '{raw_id}' must be an integer")
        
    name = str(data.get("name") or "")
    code = data.get("code")
    ecosystem = data.get("ecosystem", "Erha")
    raw_status = data.get("status", 1)
    is_inactive = str(raw_status).strip() == "0"
    
    stmt = select(Branch).where(
        func.lower(Branch.ecosystem) == ecosystem.lower(),
        Branch.external_id == external_id
    )
    branch = (await db.execute(stmt)).scalar_one_or_none()
    
    if not branch:
        branch = Branch(
            external_id=external_id,
            name=name,
            code=code,
            ecosystem=ecosystem
        )
        if is_inactive:
            branch.deleted_at = datetime.now(timezone.utc)
        db.add(branch)
    else:
        branch.name = name
        branch.code = code
        branch.ecosystem = ecosystem
        if is_inactive:
            branch.deleted_at = datetime.now(timezone.utc)
        else:
            branch.deleted_at = None
        
    await db.flush()
    return branch

async def upsert_branch_payload(db: AsyncSession, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Union[Branch, List[Branch]]:
    """Upsert branch records from pushed webhook data payload (supports single item or list)."""
    if isinstance(data, list):
        branches = []
        for item in data:
            if isinstance(item, dict):
                try:
                    branches.append(await _upsert_single_branch(db, item))
                except Exception as e:
                    logger.warning(f"Skipping malformed branch record in list payload: {e}")
        return branches
    return await _upsert_single_branch(db, data)

async def delete_branch_payload(db: AsyncSession, branch_id: Any, ecosystem: Optional[str] = None):
    """Soft delete a branch record."""
    external_id = parse_cis_int(branch_id)
    if external_id is None:
        return
    stmt = select(Branch).where(Branch.external_id == external_id)
    if ecosystem:
        stmt = stmt.where(func.lower(Branch.ecosystem) == ecosystem.lower())
    branch = (await db.execute(stmt)).scalar_one_or_none()
    if branch:
        branch.deleted_at = datetime.now(timezone.utc)
        await db.flush()

async def _upsert_single_doctor(db: AsyncSession, data: Dict[str, Any]) -> User:
    """Upsert an individual doctor record from pushed payload, including nested user_branchs."""
    if not isinstance(data, dict):
        raise ValueError(f"Invalid doctor data: expected dict, got {type(data).__name__}")
        
    raw_id = data.get("id") or data.get("cis_id") or data.get("doctor_cis_id")
    cis_id = parse_cis_int(raw_id)
    if cis_id is None:
        raise ValueError(f"Invalid or missing doctor id in payload: '{raw_id}' must be an integer")
        
    name = str(data.get("name") or "")
    raw_email = data.get("email")
    email = raw_email.strip() if isinstance(raw_email, str) and raw_email.strip() else None
    if email and ("@" not in email or len(email) < 5):
        email = None

    # Protect against unique constraint crash if another doctor has this email in DB
    if email:
        email_stmt = select(User).where(User.email == email, User.cis_id != cis_id)
        existing_email_user = (await db.execute(email_stmt)).scalar_one_or_none()
        if existing_email_user:
            logger.warning(f"Email '{email}' already assigned to user {existing_email_user.id}. Setting email to None for CIS doctor {cis_id}.")
            email = None

    employee_id = data.get("nik") or data.get("employee_id")
    dr_type = data.get("user_type_name") or data.get("dr_type")
    user_type_code = str(data.get("user_type")) if data.get("user_type") is not None else None
    ecosystem = data.get("ecosystem", "Erha")
    raw_status = data.get("status", 1)
    is_inactive = str(raw_status).strip() == "0"
    
    stmt = select(User).where(User.cis_id == cis_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    if not user:
        user = User(
            email=email,
            name=name,
            cis_id=cis_id,
            employee_id=employee_id,
            dr_type=dr_type,
            user_type_code=user_type_code,
            ecosystem=ecosystem,
            type=UserType.DOCTOR,
            token_limit=None
        )
        if is_inactive:
            user.deleted_at = datetime.now(timezone.utc)
        db.add(user)
    else:
        user.name = name
        user.email = email
        user.employee_id = employee_id
        user.dr_type = dr_type
        if user_type_code:
            user.user_type_code = user_type_code
        user.ecosystem = ecosystem
        if is_inactive:
            user.deleted_at = datetime.now(timezone.utc)
        else:
            user.deleted_at = None
        
    await db.flush()

    # Process nested branch associations if provided in doctor payload
    branches_list = data.get("user_branchs") or data.get("user_branches") or data.get("branches")
    if branches_list and isinstance(branches_list, list):
        seen_branches = set()
        for item in branches_list:
            if not isinstance(item, dict):
                continue
            b_raw_id = item.get("branch_id") or item.get("id")
            b_code = item.get("branch_code") or item.get("code")
            
            dedup_key = (str(b_raw_id) if b_raw_id is not None else None, str(b_code) if b_code else None)
            if dedup_key in seen_branches:
                continue
            seen_branches.add(dedup_key)
            
            branch = None
            if b_code:
                b_stmt = select(Branch).where(
                    func.lower(Branch.ecosystem) == user.ecosystem.lower(),
                    Branch.code == b_code
                )
                branch = (await db.execute(b_stmt)).scalar_one_or_none()
            
            if not branch and b_raw_id is not None:
                b_ext_id = parse_cis_int(b_raw_id)
                if b_ext_id is not None:
                    b_stmt = select(Branch).where(
                        func.lower(Branch.ecosystem) == user.ecosystem.lower(),
                        Branch.external_id == b_ext_id
                    )
                    branch = (await db.execute(b_stmt)).scalar_one_or_none()

            if not branch:
                logger.warning(f"Branch not found for doctor branch mapping: {item}")
                continue

            ub_stmt = select(UserBranch).where(UserBranch.user_id == user.id, UserBranch.branch_id == branch.id)
            ub = (await db.execute(ub_stmt)).scalar_one_or_none()
            
            status_val = 0 if str(item.get("status", 1)).strip() == "0" else 1

            if not ub:
                ub = UserBranch(user_id=user.id, branch_id=branch.id, status=status_val)
                if status_val == 0:
                    ub.deleted_at = datetime.now(timezone.utc)
                db.add(ub)
            else:
                ub.status = status_val
                if status_val == 0:
                    ub.deleted_at = datetime.now(timezone.utc)
                else:
                    ub.deleted_at = None
                    
        await db.flush()

    return user

async def upsert_doctor_payload(db: AsyncSession, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Union[User, List[User]]:
    """Upsert doctor records from pushed webhook payload (supports single item or list)."""
    if isinstance(data, list):
        doctors = []
        for item in data:
            if isinstance(item, dict):
                try:
                    doctors.append(await _upsert_single_doctor(db, item))
                except Exception as e:
                    logger.warning(f"Skipping malformed doctor record in list payload: {e}")
        return doctors
    return await _upsert_single_doctor(db, data)

async def upsert_user_branch_payload(db: AsyncSession, data_list: Union[Dict[str, Any], List[Dict[str, Any]]]):
    """Process a list of user-branch association updates."""
    if isinstance(data_list, dict):
        data_list = [data_list]
    elif not isinstance(data_list, list):
        data_list = []
        
    seen_mappings = set()
    for item in data_list:
        if not isinstance(item, dict):
            continue
        raw_user_id = item.get("user_id") or item.get("doctor_id") or item.get("cis_id")
        raw_branch_id = item.get("branch_id")
        branch_code = item.get("branch_code") or item.get("code")
        
        if raw_user_id is None or (raw_branch_id is None and not branch_code):
            logger.warning(f"Skipping user_branch mapping, missing user_id or branch info: {item}")
            continue
            
        dedup_key = (str(raw_user_id), str(raw_branch_id) if raw_branch_id is not None else None, str(branch_code) if branch_code else None)
        if dedup_key in seen_mappings:
            continue
        seen_mappings.add(dedup_key)
            
        user_cis_id = parse_cis_int(raw_user_id)
        if user_cis_id is None:
            logger.warning(f"Skipping user_branch mapping, invalid user_id: {raw_user_id}")
            continue
        
        u_stmt = select(User).where(User.cis_id == user_cis_id)
        user = (await db.execute(u_stmt)).scalar_one_or_none()
        
        if not user:
            logger.warning(f"Skipping user_branch mapping, user ({user_cis_id}) not found")
            continue

        branch = None
        if branch_code:
            b_stmt = select(Branch).where(
                func.lower(Branch.ecosystem) == user.ecosystem.lower(),
                Branch.code == branch_code
            )
            branch = (await db.execute(b_stmt)).scalar_one_or_none()
            
        if not branch and raw_branch_id is not None:
            branch_external_id = parse_cis_int(raw_branch_id)
            if branch_external_id is not None:
                b_stmt = select(Branch).where(
                    func.lower(Branch.ecosystem) == user.ecosystem.lower(),
                    Branch.external_id == branch_external_id
                )
                branch = (await db.execute(b_stmt)).scalar_one_or_none()
        
        if not branch:
            logger.warning(f"Skipping user_branch mapping, branch not found for user ({user_cis_id}): {item}")
            continue
            
        ub_stmt = select(UserBranch).where(UserBranch.user_id == user.id, UserBranch.branch_id == branch.id)
        ub = (await db.execute(ub_stmt)).scalar_one_or_none()
        
        status_val = 0 if str(item.get("status", 1)).strip() == "0" else 1
            
        if not ub:
            ub = UserBranch(user_id=user.id, branch_id=branch.id, status=status_val)
            if status_val == 0:
                ub.deleted_at = datetime.now(timezone.utc)
            db.add(ub)
        else:
            ub.status = status_val
            if status_val == 0:
                ub.deleted_at = datetime.now(timezone.utc)
            else:
                ub.deleted_at = None
                
    await db.flush()

async def delete_doctor_payload(db: AsyncSession, cis_id: Any):
    """Soft delete a doctor record."""
    doctor_cis_id = parse_cis_int(cis_id)
    if doctor_cis_id is None:
        return
    stmt = select(User).where(User.cis_id == doctor_cis_id, User.type == UserType.DOCTOR)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user:
        user.deleted_at = datetime.now(timezone.utc)
        await db.flush()

async def bulk_sync_payload(db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a full bulk sync payload containing branches, users/doctors, and user_branches lists.
    
    Supports key aliases:
    - branches: 'branches', 'branch'
    - users: 'users', 'doctors', 'doctor'
    - user_branches: 'user_branches', 'user_branchs', 'doctor_branches'
    
    Safety guards:
    - Pruning (soft-deleting local omitted records) is ONLY triggered if 'prune_omitted' is True.
    - Pruning is strictly scoped to the ecosystems present in the incoming payload.
    - Individual malformed records are safely skipped with a warning to protect the batch.
    """
    raw_branches = data.get("branches") or data.get("branch") or []
    branches_data = raw_branches if isinstance(raw_branches, list) else [raw_branches]
    
    raw_doctors = data.get("users") or data.get("doctors") or data.get("doctor") or []
    doctors_data = raw_doctors if isinstance(raw_doctors, list) else [raw_doctors]
    
    raw_user_branches = data.get("user_branches") or data.get("user_branchs") or data.get("doctor_branches") or []
    user_branches_data = raw_user_branches if isinstance(raw_user_branches, list) else [raw_user_branches]
    
    prune_omitted = bool(data.get("prune_omitted", False))
    
    # 1. Upsert all branches
    pulled_branch_keys = set()
    pulled_branch_ecosystems = set()
    for b_data in branches_data:
        if not isinstance(b_data, dict):
            continue
        try:
            branch = await _upsert_single_branch(db, b_data)
            if branch.external_id is not None:
                pulled_branch_keys.add((branch.ecosystem.lower(), branch.external_id))
                pulled_branch_ecosystems.add(branch.ecosystem.lower())
        except Exception as e:
            logger.warning(f"Skipping malformed branch record in bulk sync {b_data}: {e}")
        
    # Soft delete local branches omitted from full sync ONLY if explicitly requested
    if prune_omitted and pulled_branch_keys:
        all_b_stmt = select(Branch).where(Branch.deleted_at.is_(None))
        all_branches = (await db.execute(all_b_stmt)).scalars().all()
        for b in all_branches:
            if (
                b.external_id is not None 
                and b.ecosystem.lower() in pulled_branch_ecosystems
                and (b.ecosystem.lower(), b.external_id) not in pulled_branch_keys
            ):
                b.deleted_at = datetime.now(timezone.utc)
            
    # 2. Upsert all doctors
    pulled_doc_cis_ids = set()
    pulled_doc_ecosystems = set()
    for d_data in doctors_data:
        if not isinstance(d_data, dict):
            continue
        try:
            doctor = await _upsert_single_doctor(db, d_data)
            if doctor.cis_id is not None:
                pulled_doc_cis_ids.add(doctor.cis_id)
                pulled_doc_ecosystems.add(doctor.ecosystem.lower())
        except Exception as e:
            logger.warning(f"Skipping malformed doctor record in bulk sync {d_data}: {e}")
        
    # Soft delete local doctors omitted from full sync ONLY if explicitly requested
    if prune_omitted and pulled_doc_cis_ids:
        all_d_stmt = select(User).where(User.type == UserType.DOCTOR, User.deleted_at.is_(None))
        all_doctors = (await db.execute(all_d_stmt)).scalars().all()
        for d in all_doctors:
            if (
                d.cis_id is not None 
                and d.ecosystem.lower() in pulled_doc_ecosystems
                and d.cis_id not in pulled_doc_cis_ids
            ):
                d.deleted_at = datetime.now(timezone.utc)
            
    await db.flush()
    
    # 3. Process direct doctor-branch mappings if provided
    if user_branches_data:
        await upsert_user_branch_payload(db, user_branches_data)
        
    return {
        "branches_count": len([b for b in branches_data if isinstance(b, dict)]),
        "doctors_count": len([d for d in doctors_data if isinstance(d, dict)]),
        "user_branches_count": len([m for m in user_branches_data if isinstance(m, dict)]),
        "prune_omitted": prune_omitted
    }
