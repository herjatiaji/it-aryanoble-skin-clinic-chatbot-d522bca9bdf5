export type ChatStatus = "ACTIVE" | "COMPLETED" | "TIMEOUT";
export type ChatRole = "USER" | "AI" | "SYSTEM" | "HUMAN_AGENT";
export type ChatRating = "1" | "2" | "3" | "4" | "5";

export interface ChatSessionBase {
  branch_id: string; // UUID
}

export interface ChatSessionResponse extends ChatSessionBase {
  id: string;
  user_id: string;
  status: ChatStatus;
  summary?: string | null;
  rating?: ChatRating | null;
  feedback?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryResponse extends ChatSessionResponse {
  query: string;
  messages: number;
  doctor: string;
  branch: string;
}
