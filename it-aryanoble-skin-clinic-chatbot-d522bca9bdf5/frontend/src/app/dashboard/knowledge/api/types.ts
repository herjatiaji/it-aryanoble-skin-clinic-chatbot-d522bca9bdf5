export type KnowledgeType = "PRODUCT" | "TREATMENT" | "PROMOTIONAL";
export type KnowledgeStatus = "PENDING" | "PROCESSING" | "APPROVED" | "REJECTED";

export interface KnowledgeCreate {
	title: string;
	content?: string | null;
	file_name: string;
	original_path: string;
	mime_type?: string | null;
	file_size?: number | null;
	type: KnowledgeType;
}

export interface KnowledgeResponse {
	id: string; // UUID
	title: string;
	content?: string | null;
	file_name: string;
	original_path: string;
	mime_type?: string | null;
	file_size?: number | null;
	type: KnowledgeType;
	status: KnowledgeStatus;
	ai_summary?: string | null;
	ai_confidence?: number | null;
	uploaded_by: string; // UUID
	approved_by?: string | null; // UUID
	metadata?: Record<string, unknown> | null;
	created_at: string;
	updated_at: string;
}
