import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/axios";
import { doctorChatKeys } from "../api/keys";
import type { 
  ChatSessionResponse, 
  ChatHistoryResponse, 
  ChatMessageResponse
} from "../api/types";
import { getErrorMessage } from "@/lib/utils";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

export const useChatSessions = () => {
  return useQuery({
    queryKey: doctorChatKeys.sessions(),
    queryFn: async (): Promise<ChatHistoryResponse[]> => {
      const response = await api.get("/chats/");
      return response.data;
    },
  });
};

export const useCreateChatSession = () => {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: async ({ 
      branch_id, 
      initialMessageFormData 
    }: { 
      branch_id?: string | null, 
      initialMessageFormData?: FormData 
    }): Promise<ChatSessionResponse> => {
      const response = await api.post("/chats/", { branch_id });
      const session = response.data;

      if (initialMessageFormData) {
        await api.post(`/chats/${session.id}/messages`, initialMessageFormData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        });
      }

      return session;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: doctorChatKeys.sessions() });
      router.push(`/doctor/chat/${data.id}`);
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, "Failed to start chat session"));
    },
  });
};

export const useChatMessages = (sessionId: string) => {
  return useQuery({
    queryKey: doctorChatKeys.messages(sessionId),
    queryFn: async (): Promise<ChatMessageResponse[]> => {
      const response = await api.get(`/chats/${sessionId}/messages`);
      return response.data;
    },
    enabled: !!sessionId,
    refetchInterval: 3000, // Poll every 3 seconds for new messages
  });
};

export const useSendMessage = (sessionId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (formData: FormData): Promise<ChatMessageResponse> => {
      const response = await api.post(`/chats/${sessionId}/messages`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: doctorChatKeys.messages(sessionId) });
      queryClient.invalidateQueries({ queryKey: doctorChatKeys.sessions() });
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, "Failed to send message"));
    },
  });
};
