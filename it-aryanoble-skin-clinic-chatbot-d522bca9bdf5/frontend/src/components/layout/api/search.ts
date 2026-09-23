import { api } from "@/lib/axios";

export interface KnowledgeSearchResult {
	id: string;
	title: string;
	type: string;
	categories: string[];
	project_name?: string | null;
	project_id?: string | null;
	file_name?: string | null;
	snippet?: string | null;
	match_field: "title" | "summary" | "chunk_content" | "file_name" | "project" | "category";
	status: string;
	created_at?: string | null;
}

export interface ProjectSearchResult {
	id: string;
	name: string;
	description?: string | null;
	document_count: number;
	created_at?: string | null;
}

export interface CategorySearchResult {
	id: string;
	name: string;
	description?: string | null;
	knowledge_count: number;
	created_at?: string | null;
}

export interface ChatSearchResult {
	id: string;
	title: string;
	doctor_name: string;
	branch_name?: string | null;
	session_type: string;
	message_count: number;
	snippet?: string | null;
	match_role?: string | null;
	created_at?: string | null;
	updated_at?: string | null;
}

export interface UnifiedSearchResponse {
	query: string;
	total_results: number;
	knowledge: KnowledgeSearchResult[];
	projects: ProjectSearchResult[];
	categories: CategorySearchResult[];
	chats: ChatSearchResult[];
}

export async function searchGlobal(
	query: string,
	category: "all" | "knowledge" | "projects" | "categories" | "chats" = "all",
	limit: number = 8,
): Promise<UnifiedSearchResponse> {
	if (!query.trim()) {
		return { query: "", total_results: 0, knowledge: [], projects: [], categories: [], chats: [] };
	}

	const response = await api.get<UnifiedSearchResponse>("/search/", {
		params: {
			q: query.trim(),
			category,
			limit,
		},
	});
	return response.data;
}
