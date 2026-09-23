from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from app.models.knowledge import KnowledgeType, KnowledgeStatus

class KnowledgeBase(BaseModel):
    title: str
    content: Optional[str] = None
    file_name: str
    original_path: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None

class KnowledgeCreate(KnowledgeBase):
    type: KnowledgeType

class KnowledgeUpdateStatus(BaseModel):
    status: KnowledgeStatus

class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    ai_summary: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="metadata")
    project_id: Optional[UUID] = None

class KnowledgeProjectUpdate(BaseModel):
    project_id: Optional[UUID] = None

class KnowledgeTextIngestRequest(BaseModel):
    text_content: str = Field(..., description="Raw text knowledge material to convert to structured .md document")
    title: Optional[str] = Field(None, description="Optional document title")
    prompt: Optional[str] = Field(None, description="Optional custom AI processing instruction")
    project_id: Optional[UUID] = Field(None, description="Optional project ID to associate with")
    replace_existing: bool = Field(False, description="Set to true to overwrite existing pending draft")

class KnowledgeTextIngestResponse(BaseModel):
    status: str
    knowledge_id: str
    file_name: str
    title: str
    original_s3_key: Optional[str] = None
    message: str

class KnowledgeResponse(KnowledgeBase):
    id: UUID
    type: KnowledgeType
    status: KnowledgeStatus
    ai_summary: Optional[str] = None
    ai_confidence: Optional[float] = None
    uploaded_by: UUID
    uploaded_by_name: Optional[str] = None
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    project_id: Optional[UUID] = None
    metadata_: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class GeneralChatMessageItem(BaseModel):
    id: UUID
    role: str
    content: str
    action: Optional[str] = None
    type: Optional[str] = None
    operation_id: Optional[str] = None
    operation_status: Optional[str] = None
    target_knowledge_id: Optional[str] = None
    total_found: Optional[int] = None
    attachments: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class GeneralChatSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    session_type: str
    status: str
    messages: List[GeneralChatMessageItem] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class GeneralChatMessageSendRequest(BaseModel):
    prompt: str
    attachments: Optional[Dict[str, Any]] = None

class BatchVisibilityUpdateRequest(BaseModel):
    visibility_settings: Dict[str, Any]

