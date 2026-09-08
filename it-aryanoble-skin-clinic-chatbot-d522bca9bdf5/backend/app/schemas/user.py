from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.user import UserType
from app.schemas.branch import BranchResponse
from app.schemas.category import CategoryResponse

class RoleResponse(BaseModel):
    id: UUID
    name: str
    model_config = ConfigDict(from_attributes=True)

class UserBase(BaseModel):
    email: EmailStr
    name: str

class UserCreateStaff(UserBase):
    password: str
    employee_id: Optional[str] = None
    roles: Optional[List[str]] = ["Staff"]

class StaffUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    password: Optional[str] = None
    status: Optional[str] = None

class DoctorUpdate(BaseModel):
    token_limit: Optional[int] = None
    status: Optional[str] = None
    employee_id: Optional[str] = None
    dr_type: Optional[str] = None
    ecosystem: Optional[str] = None

class UserUpdateRoles(BaseModel):
    roles: List[str]

class UserUpdateBranches(BaseModel):
    branches: List[UUID]

class UserUpdateCategories(BaseModel):
    categories: List[UUID]

class UserUpdateAccesses(BaseModel):
    accesses: List[str]

class UserResponse(UserBase):
    id: UUID
    type: UserType
    cis_id: Optional[str] = None
    token_limit: Optional[int] = None
    employee_id: Optional[str] = None
    dr_type: Optional[str] = None
    ecosystem: str
    created_at: datetime
    
    status: Optional[str] = None
    tokens_used: Optional[int] = None
    roles: Optional[List[RoleResponse]] = None
    accesses: Optional[List[str]] = None
    branches: Optional[List[BranchResponse]] = None
    categories: Optional[List[CategoryResponse]] = None

    model_config = ConfigDict(from_attributes=True)
