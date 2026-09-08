export interface ChatSessionCreate {
  branch_id?: string | null;
}

export interface ChatSessionUpdate {
  status?: string;
  summary?: string;
  rating?: number;
  feedback?: string;
}

export interface ChatSessionResponse {
  id: string;
  user_id: string;
  branch_id?: string | null;
  status: string;
  summary?: string | null;
  rating?: number | null;
  feedback?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryResponse extends ChatSessionResponse {
  query: string;
  messages: number;
  doctor: string;
}

export interface ChatMessageResponse {
  id: string;
  session_id: string;
  role: string;
  content: string;
  attachments?: Record<string, unknown> | null;
  created_at: string;
}
