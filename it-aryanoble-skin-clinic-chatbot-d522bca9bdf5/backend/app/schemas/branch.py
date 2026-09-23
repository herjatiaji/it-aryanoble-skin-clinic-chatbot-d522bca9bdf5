from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class BranchBase(BaseModel):
    name: str
    token_limit: int = 0

class BranchCreate(BranchBase):
    pass

class BranchUpdate(BaseModel):
    name: Optional[str] = None
    token_limit: Optional[int] = None
    has_custom_limit: Optional[bool] = None
    reset_to_global: Optional[bool] = False

class BranchDoctorResponse(BaseModel):
    id: UUID
    name: str
    speciality: str = ""
    tokensLeft: int = 0
    tokens_used: Optional[int] = 0
    status: str = "Active"
    maxTokens: int = 0
    employee_id: Optional[str] = None
    dr_type: Optional[str] = None
    user_type_code: Optional[str] = None
    ecosystem: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class BranchResponse(BranchBase):
    id: UUID
    external_id: Optional[int] = None
    code: Optional[str] = None
    ecosystem: str = "Erha"
    created_at: datetime
    updated_at: datetime
    
    used: int = 0
    remaining: int = 0
    tokens_used: Optional[int] = 0
    has_custom_limit: Optional[bool] = False
    
    doctors: Optional[List[BranchDoctorResponse]] = []
    
    model_config = ConfigDict(from_attributes=True)
