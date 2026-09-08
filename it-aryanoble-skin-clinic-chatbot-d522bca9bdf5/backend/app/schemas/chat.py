from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from app.models.chat import ChatStatus, ChatRole, ChatRating

class ChatSessionCreate(BaseModel):
    branch_id: UUID

class ChatSessionUpdate(BaseModel):
    status: Optional[ChatStatus] = None
    summary: Optional[str] = None
    rating: Optional[ChatRating] = None
    feedback: Optional[str] = None

class ChatSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    branch_id: UUID
    status: ChatStatus
    summary: Optional[str] = None
    rating: Optional[ChatRating] = None
    feedback: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ChatHistoryResponse(ChatSessionResponse):
    query: str
    messages: int
    doctor: str
    branch: str
    
    model_config = ConfigDict(from_attributes=True)

class ChatMessageCreate(BaseModel):
    role: ChatRole
    content: str

class ChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: ChatRole
    content: str
    attachments: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
