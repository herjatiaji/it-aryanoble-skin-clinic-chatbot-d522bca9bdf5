import { api } from "@/lib/axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { branchKeys } from "../../configuration/api/keys";
import { BranchResponse, BranchUpdate } from "../../configuration/api/types";

export function useBranches() {
	return useQuery<BranchResponse[]>({
		queryKey: branchKeys.lists(),
		queryFn: async () => {
			const response = await api.get("/branches/");
			return response.data;
		},
	});
}

export function useBranch(id: string) {
	return useQuery<BranchResponse>({
		queryKey: branchKeys.detail(id),
		queryFn: async () => {
			const response = await api.get(`/branches/${id}`);
			return response.data;
		},
		enabled: !!id,
	});
}

export function useUpdateBranch() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id, data }: { id: string; data: BranchUpdate }) => {
			const response = await api.put(`/branches/${id}`, data);
			return response.data;
		},
		onSuccess: (_, variables) => {
			queryClient.invalidateQueries({ queryKey: branchKeys.lists() });
			queryClient.invalidateQueries({ queryKey: branchKeys.detail(variables.id) });
			toast.success("Branch updated successfully");
		},
		onError: (error) => {
			toast.error("Failed to update branch");
			console.error(error);
		},
	});
}

