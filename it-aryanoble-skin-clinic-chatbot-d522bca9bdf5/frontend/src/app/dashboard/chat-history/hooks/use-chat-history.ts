import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/axios";
import { chatHistoryKeys } from "../api/keys";
import type { ChatHistoryResponse } from "../api/types";

export function useChatHistories() {
  return useQuery<ChatHistoryResponse[]>({
    queryKey: chatHistoryKeys.lists(),
    queryFn: async () => {
      const response = await api.get("/chats/");
      return response.data;
    },
  });
}
