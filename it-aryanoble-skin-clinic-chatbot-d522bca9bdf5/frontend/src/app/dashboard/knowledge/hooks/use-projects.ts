import { api } from "@/lib/axios";
import { getErrorMessage } from "@/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { projectKeys, knowledgeKeys } from "../api/keys";
import type { ProjectResponse, ProjectStatsResponse, ProjectCreate, ProjectUpdate, ProjectDetailResponse } from "../api/types";

export const useProjects = (search?: string) => {
	return useQuery({
		queryKey: projectKeys.list({ search: search || "" }),
		queryFn: async (): Promise<ProjectResponse[]> => {
			const params: Record<string, string> = {};
			if (search && search.trim()) {
				params.search = search.trim();
			}
			const response = await api.get("/projects/", { params });
			return response.data;
		},
	});
};

export const useProjectStats = () => {
	return useQuery({
		queryKey: projectKeys.stats(),
		queryFn: async (): Promise<ProjectStatsResponse> => {
			const response = await api.get("/projects/stats");
			return response.data;
		},
	});
};

export const useProjectDetail = (id: string) => {
	return useQuery({
		queryKey: projectKeys.detail(id),
		queryFn: async (): Promise<ProjectDetailResponse> => {
			const response = await api.get(`/projects/${id}`);
			return response.data;
		},
		enabled: !!id,
	});
};

export const useCreateProject = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (payload: ProjectCreate): Promise<ProjectResponse> => {
			const response = await api.post("/projects/", payload);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Project created successfully!");
			queryClient.invalidateQueries({ queryKey: projectKeys.all, refetchType: "all" });
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all, refetchType: "all" });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to create project."));
		},
	});
};

export const useUpdateProject = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id, data }: { id: string; data: ProjectUpdate }): Promise<ProjectResponse> => {
			const response = await api.put(`/projects/${id}`, data);
			return response.data;
		},
		onSuccess: (_, variables) => {
			toast.success("Project updated successfully!");
			queryClient.invalidateQueries({ queryKey: projectKeys.all, refetchType: "all" });
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all, refetchType: "all" });
			if (variables?.id) {
				queryClient.invalidateQueries({ queryKey: projectKeys.detail(variables.id), refetchType: "all" });
			}
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to update project."));
		},
	});
};

export const useDeleteProject = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (id: string): Promise<void> => {
			await api.delete(`/projects/${id}`);
		},
		onSuccess: () => {
			toast.success("Project deleted successfully!");
			queryClient.invalidateQueries({ queryKey: projectKeys.all, refetchType: "all" });
			queryClient.invalidateQueries({ queryKey: knowledgeKeys.all, refetchType: "all" });
			queryClient.invalidateQueries({ queryKey: ["knowledge-batch"], refetchType: "all" });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to delete project."));
		},
	});
};
