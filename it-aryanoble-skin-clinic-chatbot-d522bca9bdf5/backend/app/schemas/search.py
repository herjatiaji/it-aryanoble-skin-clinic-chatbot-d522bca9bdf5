from typing import List, Optional
import uuid
from datetime import datetime
from pydantic import BaseModel

class KnowledgeSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    type: str
    categories: List[str] = []
    project_name: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    file_name: Optional[str] = None
    snippet: Optional[str] = None
    match_field: str # 'title', 'summary', 'chunk_content', 'file_name', 'project', 'category'
    status: str
    created_at: Optional[datetime] = None

class ProjectSearchResult(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    document_count: int = 0
    created_at: Optional[datetime] = None

class CategorySearchResult(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    knowledge_count: int = 0
    created_at: Optional[datetime] = None

class ChatSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    doctor_name: str
    branch_name: Optional[str] = None
    session_type: str
    message_count: int
    snippet: Optional[str] = None
    match_role: Optional[str] = None # 'USER', 'ASSISTANT', 'SYSTEM', 'SUMMARY'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UnifiedSearchResponse(BaseModel):
    query: str
    total_results: int
    knowledge: List[KnowledgeSearchResult] = []
    projects: List[ProjectSearchResult] = []
    categories: List[CategorySearchResult] = []
    chats: List[ChatSearchResult] = []
