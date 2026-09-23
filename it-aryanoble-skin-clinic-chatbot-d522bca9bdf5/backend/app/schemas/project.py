from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.schemas.knowledge import KnowledgeResponse

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class ProjectResponse(ProjectBase):
    id: UUID
    created_by: Optional[UUID] = None
    total_knowledges: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ProjectStatsResponse(BaseModel):
    total_projects: int
    total_knowledge: int

class ProjectDetailResponse(ProjectResponse):
    knowledges: List[KnowledgeResponse] = []
