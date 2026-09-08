import { api } from "@/lib/axios";
import { getErrorMessage } from "@/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { knowledgeKeys } from "../api/keys";
import type { KnowledgeResponse, KnowledgeStatus } from "../api/types";

export const useKnowledgeBaseList = () => {
	return useQuery({
		queryKey: knowledgeKeys.all,
		queryFn: async (): Promise<KnowledgeResponse[]> => {
			const response = await api.get("/knowledge/");
			return response.data;
		},
		refetchInterval: (query) => {
			const data = query.state.data;
			if (data?.some((item) => item.status === "PROCESSING")) {
				return 3000;
			}
			return false;
		},
	});
};

export const useKnowledgeDetail = (id: string) => {
	return useQuery({
		queryKey: knowledgeKeys.detail(id),
		queryFn: async (): Promise<KnowledgeResponse> => {
			const response = await api.get(`/knowledge/${id}`);
			return response.data;
		},
		enabled: !!id,
		refetchInterval: (query) => {
			const data = query.state.data;
			if (data?.status === "PROCESSING") {
				return 1500;
			}
			return false;
		},
	});
};

export const useUploadKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (formData: FormData) => {
			const response = await api.post("/ai/ingest", formData);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Files uploaded successfully!");
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to upload knowledge files."));
		},
	});
};

export const useUpdateKnowledgeStatus = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id, status }: { id: string; status: KnowledgeStatus }) => {
			const response = await api.patch(`/knowledge/${id}/status`, { status });
			return response.data;
		},
		onSuccess: (_, variables) => {
			toast.success("Status updated successfully!");
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
			if (variables?.id) {
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(variables.id) });
			}
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to update status."));
		},
	});
};

export const useApproveKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (id: string) => {
			const response = await api.post(`/ai/ingest/approve/${id}`);
			return response.data;
		},
		onSuccess: (_, id) => {
			toast.success("Document approved and indexed into AI Knowledge Base!");
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(id) });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to approve and index document."));
		},
	});
};

export const useUpdateKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			id,
			data,
		}: {
			id: string;
			data: {
				title?: string;
				content?: string;
				ai_summary?: string;
				type?: string;
				metadata?: Record<string, any>;
			};
		}) => {
			const response = await api.put(`/knowledge/${id}`, data);
			return response.data;
		},
		onSuccess: (_, variables) => {
			toast.success("Knowledge document updated successfully!");
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
			if (variables?.id) {
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(variables.id) });
			}
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to update knowledge document."));
		},
	});
};

export const useDeleteKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (id: string) => {
			const response = await api.delete(`/knowledge/${id}`);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Knowledge deleted successfully!");
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to delete knowledge document."));
		},
	});
};
