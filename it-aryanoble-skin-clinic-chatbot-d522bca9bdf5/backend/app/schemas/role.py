from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class AccessResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class RoleResponse(BaseModel):
    id: UUID
    name: str
    accesses: List[str] = []
    user_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class RoleCreate(BaseModel):
    name: str
    accesses: List[str] = []

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    accesses: Optional[List[str]] = None
