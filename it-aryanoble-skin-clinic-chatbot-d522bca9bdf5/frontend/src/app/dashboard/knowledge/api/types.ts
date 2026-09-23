export type KnowledgeType = "PRODUCT" | "TREATMENT" | "PROMOTIONAL" | "GENERAL" | "OTHER";
export type KnowledgeStatus = "PENDING" | "PROCESSING" | "APPROVED" | "REJECTED";

export interface KnowledgeCreate {
	title: string;
	content?: string | null;
	file_name: string;
	original_path: string;
	mime_type?: string | null;
	file_size?: number | null;
	type?: KnowledgeType;
	project_id?: string | null;
}

export interface KnowledgeTextIngestRequest {
	text_content: string;
	title?: string | null;
	prompt?: string | null;
	project_id?: string | null;
	replace_existing?: boolean;
}

export interface KnowledgeTextIngestResponse {
	status: string;
	knowledge_id: string;
	file_name: string;
	title: string;
	original_s3_key?: string | null;
	message: string;
}

export interface VisibilitySettings {
	clinics: string[];
	doctor_types: string[];
	doctors: string[];
}

export interface KnowledgeChunkMetadata {
	knowledge_id?: string;
	chunk_index?: number;
	section?: string;
	section_name?: string;
	heading?: string;
	heading_path?: string | string[];
	page?: number;
	title?: string;
	categories?: string[];
	category?: string;
	is_custom?: boolean;
	[key: string]: unknown;
}

export interface KnowledgeChunkItem {
	text: string;
	metadata?: KnowledgeChunkMetadata;
}

export interface KnowledgeEditRequest {
	summary: string;
	categories: string[];
	visibility_settings?: VisibilitySettings;
	title?: string;
	chunks?: KnowledgeChunkItem[];
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
	uploaded_by_name?: string | null;
	approved_by?: string | null; // UUID
	approved_at?: string | null;
	project_id?: string | null; // UUID
	metadata?: {
		visibility_settings?: VisibilitySettings;
		categories?: string[];
		suggested_categories?: Array<{ id?: string | null; name: string }>;
		chunks?: KnowledgeChunkItem[];
		batch_id?: string;
		upload_batch_id?: string;
		batch_summary?: string;
		[key: string]: unknown;
	} | null;
	created_at: string;
	updated_at: string;
}

export interface ProjectResponse {
	id: string; // UUID
	name: string;
	description?: string | null;
	created_by?: string | null;
	total_knowledges: number;
	created_at: string;
	updated_at: string;
}

export interface ProjectDetailResponse {
	id: string; // UUID
	name: string;
	description?: string | null;
	created_by?: string | null;
	total_knowledges: number;
	knowledges: KnowledgeResponse[];
	created_at: string;
	updated_at: string;
}

export interface ProjectStatsResponse {
	total_projects: number;
	total_knowledge: number;
}

export interface ProjectCreate {
	name: string;
	description?: string | null;
}

export interface ProjectUpdate {
	name?: string;
	description?: string | null;
}

export function extractKnowledgeCategories(doc?: KnowledgeResponse | null): string[] {
	if (!doc || !doc.metadata) return [];
	const meta = doc.metadata as Record<string, unknown>;
	const catSet = new Set<string>();

	// 1. Direct categories
	const directCats = meta.categories;
	if (Array.isArray(directCats)) {
		for (const c of directCats) {
			if (typeof c === "string" && c.trim()) {
				catSet.add(c.trim());
			} else if (
				c &&
				typeof c === "object" &&
				"name" in c &&
				typeof (c as { name: unknown }).name === "string"
			) {
				const n = (c as { name: string }).name.trim();
				if (n) catSet.add(n);
			}
		}
	}

	// 2. Suggested categories
	const suggestedCats = meta.suggested_categories;
	if (Array.isArray(suggestedCats)) {
		for (const c of suggestedCats) {
			if (typeof c === "string" && c.trim()) {
				catSet.add(c.trim());
			} else if (
				c &&
				typeof c === "object" &&
				"name" in c &&
				typeof (c as { name: unknown }).name === "string"
			) {
				const n = (c as { name: string }).name.trim();
				if (n) catSet.add(n);
			}
		}
	}

	return Array.from(catSet);
}
