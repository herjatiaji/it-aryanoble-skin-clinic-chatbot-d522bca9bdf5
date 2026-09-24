from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the sender ('user' or 'assistant')")
    content: str = Field(..., description="Content of the conversation message")

class UserContext(BaseModel):
    user_id: str = Field(..., description="The ID of the user requesting the chat")
    dr_type: str = Field(..., description="The doctor type of the user")
    branch_ids: List[str] = Field(default_factory=list, description="The branch IDs the user belongs to")
    excluded_categories: List[str] = Field(default_factory=list, description="The names of categories excluded for this user")
    doctor_name: Optional[str] = Field(None, description="The name of the doctor (e.g. 'dr. Sarah' or 'Sarah')")

class ChatRequest(BaseModel):
    query: str = Field(..., description="User question or medical query string")
    categories: Optional[List[str]] = Field(default=[], description="Optional list of category filters (e.g. ['Acne Care', 'Brightening'])")
    top_k: int = Field(8, description="Number of context passages to retrieve")
    history: List[ChatMessage] = Field(default=[], description="Multi-turn conversation chat history context")
    user_context: Optional[UserContext] = Field(None, description="Context properties of the querying user used for visibility and exclusion filtering")
    attachment_text: Optional[str] = Field(None, description="Extracted text from attached patient document/profile (auto-populated by backend when file is uploaded)")
    doctor_name: Optional[str] = Field(None, description="The name of the doctor (e.g. 'dr. Sarah' or 'Sarah')")
    knowledge_id: Optional[str] = Field(None, description="Target knowledge ID to scope query strictly to this document if specified")
    knowledge_ids: Optional[List[str]] = Field(default=[], description="Target knowledge IDs to scope query strictly to these documents")
    batch_id: Optional[str] = Field(None, description="Target batch ID to scope query strictly to this batch")


class ChatResponse(BaseModel):
    query: str = Field(..., description="User query string")
    answer: str = Field(..., description="Doctor-aligned AI generated response")
    context: str = Field(..., description="Retrieved context passages formatted for reference")
    results: List[Dict[str, Any]] = Field(..., description="Retrieved passage citations and metadata")
    agent_used: bool = Field(False, description="Whether AI Agent (multi-step reasoning) was used for this response")

class EvaluationItem(BaseModel):
    query: str = Field(..., description="Test query string (e.g. 'Apa indikasi ERHA Acne Clear Gel?')")
    expected_file: str = Field(..., description="Expected source document filename (e.g. 'ERHA Acne Clear Gel.docx')")

class TextIngestRequest(BaseModel):
    text_content: str = Field(..., description="Raw text knowledge material to convert to structured .md document")
    title: Optional[str] = Field(None, description="Optional document title (auto-generated if not specified)")
    prompt: Optional[str] = Field(None, description="Optional custom AI processing instruction")
    project_id: Optional[str] = Field(None, description="Optional target project ID to assign document to")
    replace_existing: bool = Field(False, description="Set to true to overwrite existing pending draft")


class DocumentListItem(BaseModel):
    knowledge_id: str = Field(..., description="Unique document ID (UUID)")
    batch_id: Optional[str] = Field(None, description="Batch Upload ID for grouped ingestion tracking")
    file_name: str = Field(..., description="Filename of the ingested document")
    product_name: Optional[str] = Field(None, description="Extracted product name")
    status: str = Field(..., description="'Approved' or 'On review'")
    processed_at: Optional[str] = Field(None, description="ISO timestamp of when document was processed")
    chunks_count: int = Field(..., description="Number of text chunks in document")

class ApproveRequest(BaseModel):
    file_name: Optional[str] = Field(None, description="Filename of the pending document to approve")
    category_ids: Optional[List[str]] = Field(default=[], description="Category IDs if applicable")
    knowledge_ids: Optional[List[str]] = Field(default=[], description="Optional list of knowledge IDs for batch approval in 1 click")

class RejectRequest(BaseModel):
    file_name: Optional[str] = Field(None, description="Filename of the pending document to reject")

class VisibilitySettings(BaseModel):
    clinics: List[str] = Field(default=["all"], description="Allowed clinic IDs or ['all']")
    doctor_types: List[str] = Field(default=["all"], description="Allowed doctor type IDs or ['all']")
    doctors: List[str] = Field(default=["all"], description="Allowed doctor user IDs or ['all']")

class PendingDocumentResponse(BaseModel):
    knowledge_id: str = Field(..., description="Unique document ID (UUID)")
    batch_id: Optional[str] = Field(None, description="Batch Upload ID for grouped ingestion tracking")
    file_name: str = Field(..., description="Filename of the staged document")
    file_hash: Optional[str] = Field(None, description="SHA-256 Checksum hash of the document content")
    title: Optional[str] = Field(None, description="AI Recommended Title for Knowledge Header (e.g. 'Standard Operating Procedure (SOP) Brightening Center')")
    status: str = Field(..., description="'Approved' or 'On review'")
    document_type: Optional[str] = Field(None, description="Document type e.g. 'PRODUCT', 'TREATMENT', 'PROMOTIONAL', 'SOP', 'GENERAL'")
    summary: Optional[str] = Field("", description="Document content in markdown format")
    image_urls: Optional[List[str]] = Field(default=[], description="All extracted image URLs of the document in MinIO")
    text_accuracy: str = Field(..., description="AI confidence score / text accuracy percentage")
    feedback: str = Field(..., description="AI data validation feedback")
    batch_summary: Optional[str] = Field(None, description="Batch Executive Summary if multi-file")
    suggested_categories: Optional[List[Any]] = Field(default=[], description="Suggested category tags (objects with id and name)")
    visibility_settings: Optional[VisibilitySettings] = Field(default_factory=VisibilitySettings, description="Access control visibility settings (Clinic, Doctor Type, Doctor)")
    initial_prompt: Optional[str] = Field(None, description="Initial prompt passed during ingestion if any")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Conversation history list")
    chunks: List[Dict[str, Any]] = Field(..., description="Parsed chunks list")
    reply: Optional[str] = Field(None, description="Direct assistant chat reply for retrieval queries")
    answer: Optional[str] = Field(None, description="Direct assistant chat answer")
    is_retrieval: Optional[bool] = Field(False, description="Whether this turn was a retrieval query")

class RefineRequest(BaseModel):
    prompt: str = Field(..., description="Instructions to refine the document summary or text content")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Multi-turn conversation history for refine editing")

    model_config = {
        "json_schema_extra": {
            "example": {
                "prompt": "Tolong terjemahkan bagian dosis ke Bahasa Indonesia dan buatkan kesimpulan",
                "history": []
            }
        }
    }

class EditApprovedDocumentRequest(BaseModel):
    summary: Optional[str] = Field(None, description="Updated document summary markdown (for manual save)")
    categories: Optional[List[Any]] = Field(default=[], description="Updated list of document categories (for manual save)")
    visibility_settings: Optional[VisibilitySettings] = Field(None, description="Updated visibility settings (Clinics, Doctor Types, Doctors)")
    title: Optional[str] = Field(None, description="Updated document title")
    document_type: Optional[str] = Field(None, description="Updated document type")
    valid_from: Optional[str] = Field(None, description="Updated valid from date (YYYY-MM-DD)")
    valid_until: Optional[str] = Field(None, description="Updated valid until / expiry date (YYYY-MM-DD)")
    chunks: Optional[List[Dict[str, Any]]] = Field(None, description="Optional updated chunks list with per-section categories/metadata")

    model_config = {
        "json_schema_extra": {
            "example": {
                "summary": "### Ringkasan Dokumen Produk\n\nProduk ini digunakan untuk merawat kulit jerawat dan menyamarkan noda hitam.",
                "categories": ["Acne Care", "Dark Spot"],
                "document_type": "PROMOTIONAL",
                "valid_from": "2026-08-01",
                "valid_until": "2026-08-31",
                "visibility_settings": {
                    "clinics": ["all"],
                    "doctor_types": ["all"],
                    "doctors": ["all"]
                }
            }
        }
    }

class ApprovedDocumentResponse(BaseModel):
    knowledge_id: str = Field(..., description="Knowledge ID / document identifier")
    batch_id: Optional[str] = Field(None, description="Batch Upload ID")
    file_name: str = Field(..., description="Filename of the approved document")
    file_hash: Optional[str] = Field(None, description="SHA-256 Checksum hash")
    title: Optional[str] = Field(None, description="Document title")
    status: str = Field("Approved", description="Document status")
    document_type: Optional[str] = Field(None, description="Document type e.g. 'PRODUCT', 'TREATMENT', 'PROMOTIONAL', 'SOP', 'GENERAL'")
    valid_from: Optional[str] = Field(None, description="Start date of promotional validity period (YYYY-MM-DD)")
    valid_until: Optional[str] = Field(None, description="End/expiration date of promotional validity period (YYYY-MM-DD)")
    summary: str = Field("", description="Document summary")
    image_urls: Optional[List[str]] = Field(default=[], description="All extracted image URLs of the document in MinIO")
    batch_summary: Optional[str] = Field(None, description="Batch Executive Summary if multi-file")
    categories: List[str] = Field(default=[], description="Document categories")
    visibility_settings: Optional[VisibilitySettings] = Field(default_factory=VisibilitySettings, description="Access control visibility settings (Clinic, Doctor Type, Doctor)")
    chunks: List[Dict[str, Any]] = Field(..., description="Document text chunks")


# --- RAGAS-style Evaluation Schemas ---

class RAGEvaluationItem(BaseModel):
    query: str = Field(..., description="Test query string (e.g. 'Berapa lama durasi tindakan Acne Intensive Program?')")
    expected_file: str = Field(..., description="Expected source document filename or keyword match (e.g. 'ERHA_Acne_Center_Treatments.docx')")
    expected_answer: Optional[str] = Field(None, description="Expected reference answer for generation evaluation (opsional)")

class RAGEvaluationRequest(BaseModel):
    dataset: Optional[List[RAGEvaluationItem]] = Field(
        None, 
        description="Optional custom benchmark test dataset. If empty, the default official ERHA benchmark dataset will be used."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "dataset": [
                    {
                        "query": "Berapa lama durasi tindakan, downtime, dan interval sesi untuk Acne Intensive Program?",
                        "expected_file": "ERHA_Acne_Center_Treatments.docx",
                        "expected_answer": "Durasi tindakan 60-75 menit, downtime 1-2 hari, interval 2 minggu sekali."
                    },
                    {
                        "query": "Apa saja kandungan aktif, indikasi, dan harga ERHA Acneact Acne Spot Gel?",
                        "expected_file": "Katalog_Acneact.pdf",
                        "expected_answer": "Kandungan BHA/Salicylic Acid, Sulfur. Indikasi jerawat aktif. Harga Rp 50.000."
                    }
                ]
            }
        }
    }

class RAGEvaluationQueryResult(BaseModel):
    query: str = Field(..., description="Test query string")
    expected_file: str = Field(..., description="Expected reference document")
    retrieved_source: Optional[str] = Field(None, description="Top retrieved document filename")
    hit: bool = Field(..., description="Whether expected document was found in top-K")
    reciprocal_rank: float = Field(..., description="1 / rank position of expected document")
    faithfulness_score: Optional[float] = Field(None, description="Faithfulness / Groundedness score (0.0 - 1.0)")
    relevance_score: Optional[float] = Field(None, description="Answer Relevance score (0.0 - 1.0)")
    generated_answer: Optional[str] = Field(None, description="Generated answer from RAG pipeline")

class RAGEvaluationResponse(BaseModel):
    hit_rate: float = Field(..., description="Hit Rate@K — proportion of queries where relevant doc is in top-K (0.0 - 1.0)")
    mrr: float = Field(..., description="Mean Reciprocal Rank@K — precision of rank positioning (0.0 - 1.0)")
    faithfulness: Optional[float] = Field(None, description="Faithfulness score (0.0 - 1.0) — zero hallucination groundedness score")
    answer_relevance: Optional[float] = Field(None, description="Answer Relevance score (0.0 - 1.0) — directness & medical accuracy score")
    overall_quality_score: float = Field(..., description="Composite RAG Quality Index (0 - 100%) for SLA readiness monitoring")
    total_queries: int = Field(..., description="Total benchmark queries evaluated")
    evaluated_at: str = Field(..., description="ISO Timestamp of benchmark execution")
    details: List[RAGEvaluationQueryResult] = Field(default=[], description="Detailed per-query evaluation breakdowns")


# --- Canonical Knowledge Model Re-exports ---
from app.rag.canonical import (
    CanonicalChunk,
    KnowledgeScope,
    KnowledgeType,
    EvidenceUnit,
    CompactEvidencePack,
    generate_stable_chunk_id,
    build_canonical_retrieval_text,
    ImageType,
    ImageRelevance,
    ImageDisplayPolicy,
    ClinicalStage,
    FORM_FACTOR_TAXONOMY,
    extract_canonical_form_factor,
    generate_stable_image_id,
    ImageProvenance,
    ImageProvenanceRegistry,
    classify_image_provenance
)
