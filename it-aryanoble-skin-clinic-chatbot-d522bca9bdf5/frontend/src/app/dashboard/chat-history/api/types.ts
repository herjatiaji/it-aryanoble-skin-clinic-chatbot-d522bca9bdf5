export type ChatStatus = "ACTIVE" | "COMPLETED" | "TIMEOUT";
export type ChatRole = "USER" | "AI" | "SYSTEM" | "HUMAN_AGENT";
export type ChatRating = "GOOD" | "BAD" | "1" | "2" | "3" | "4" | "5";

export interface ChatSessionBase {
  branch_id?: string | null; // UUID
}

export interface ChatSessionResponse extends ChatSessionBase {
  id: string;
  user_id: string;
  session_type?: string;
  status: ChatStatus;
  summary?: string | null;
  rating?: ChatRating | null;
  feedback?: string | null;
  has_data_issue?: boolean;
  is_feedback_read?: boolean;
  allow_file_attachments?: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryResponse extends ChatSessionResponse {
  query: string;
  messages: number;
  doctor: string;
  user_name?: string;
  user_type?: string;
  branch: string;
  doctor_type?: string | null;
}

export interface ChatStatsResponse {
  doctors_reached: number;
  total_sessions: number;
  positive_ratings: number;
  negative_ratings: number;
  missing_knowledge: number;
}
