import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/axios";

export interface ChatMessage {
  id: string;
  session_id: string;
  role: string;
  content: string;
  attachments?: Record<string, unknown>;
  created_at: string;
}

export const useChatMessages = (sessionId: string) => {
  return useQuery({
    queryKey: ["chat-messages", sessionId],
    queryFn: async (): Promise<ChatMessage[]> => {
      const response = await api.get(`/chats/${sessionId}/messages`);
      return response.data;
    },
    enabled: !!sessionId,
  });
};
