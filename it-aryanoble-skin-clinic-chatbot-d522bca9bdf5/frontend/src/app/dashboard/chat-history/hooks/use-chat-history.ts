import { api } from "@/lib/axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NOTIFICATION_KEYS } from "../../notifications/api/keys";
import { chatHistoryKeys } from "../api/keys";
import type { ChatHistoryResponse, ChatSessionResponse, ChatStatsResponse } from "../api/types";

export function useChatHistories(doctor_id?: string) {
	return useQuery<ChatHistoryResponse[]>({
		queryKey: doctor_id ? chatHistoryKeys.list({ doctor_id }) : chatHistoryKeys.lists(),
		queryFn: async () => {
			const params = doctor_id ? { doctor_id } : undefined;
			const response = await api.get("/chats/", { params });
			return response.data;
		},
	});
}

export function useChatStats(doctor_id?: string) {
	return useQuery<ChatStatsResponse>({
		queryKey: chatHistoryKeys.stats(doctor_id),
		queryFn: async () => {
			const params = doctor_id ? { doctor_id } : undefined;
			const response = await api.get("/chats/stats", { params });
			return response.data;
		},
	});
}

export function useChatHistoryDetail(sessionId?: string | null) {
	return useQuery<ChatHistoryResponse>({
		queryKey: sessionId ? chatHistoryKeys.detail(sessionId) : ["chat-history", "detail", "empty"],
		queryFn: async () => {
			const response = await api.get(`/chats/${sessionId}`);
			return response.data;
		},
		enabled: !!sessionId,
	});
}

export function useUpdateChatSession() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async ({
			sessionId,
			data,
		}: {
			sessionId: string;
			data: Partial<ChatSessionResponse>;
		}) => {
			const response = await api.put(`/chats/${sessionId}`, data);
			return response.data;
		},
		onSuccess: (_, variables) => {
			queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all });
			queryClient.invalidateQueries({ queryKey: chatHistoryKeys.detail(variables.sessionId) });
			queryClient.invalidateQueries({ queryKey: ["chat-messages", variables.sessionId] });
			queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEYS.all });
		},
	});
}
