from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from datetime import datetime
from app.models.chat import ChatStatus, ChatRole, ChatRating

class ChatSessionCreate(BaseModel):
    branch_code: Optional[str] = None
    branch_id: Optional[UUID] = None
    cis_branch_id: Optional[Union[int, str]] = None

class ChatSessionUpdate(BaseModel):
    status: Optional[ChatStatus] = None
    summary: Optional[str] = None
    rating: Optional[ChatRating] = None
    feedback: Optional[str] = None
    has_data_issue: Optional[bool] = None

class ChatSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    branch_id: Optional[UUID] = None
    session_type: Optional[str] = "DOCTOR"
    status: ChatStatus
    summary: Optional[str] = None
    rating: Optional[ChatRating] = None
    feedback: Optional[str] = None
    has_data_issue: bool = False
    is_feedback_read: bool = False
    allow_file_attachments: Optional[bool] = False
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ChatHistoryResponse(ChatSessionResponse):
    query: str
    messages: int
    doctor: str
    user_name: Optional[str] = None
    user_type: Optional[str] = None
    branch: str
    doctor_type: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class ChatStatsResponse(BaseModel):
    doctors_reached: int
    total_sessions: int
    positive_ratings: int
    negative_ratings: int
    missing_knowledge: int

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
