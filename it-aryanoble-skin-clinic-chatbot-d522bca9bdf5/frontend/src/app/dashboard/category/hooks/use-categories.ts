import { api } from "@/lib/axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { categoryKeys } from "../api/keys";
import { CategoryCreate, CategoryResponse, CategoryUpdate } from "../api/types";

export function useCategories() {
	return useQuery<CategoryResponse[]>({
		queryKey: categoryKeys.lists(),
		queryFn: async () => {
			const response = await api.get("/categories/");
			return response.data;
		},
	});
}

export function useCategory(id: string) {
	return useQuery<CategoryResponse>({
		queryKey: categoryKeys.detail(id),
		queryFn: async () => {
			const response = await api.get(`/categories/${id}`);
			return response.data;
		},
		enabled: !!id,
	});
}

export function useCreateCategory() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (data: CategoryCreate) => {
			const response = await api.post("/categories/", data);
			return response.data;
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: categoryKeys.lists() });
			toast.success("Category created successfully");
		},
		onError: (error) => {
			toast.error("Failed to create category");
			console.error(error);
		},
	});
}

export function useUpdateCategory() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id, data }: { id: string; data: CategoryUpdate }) => {
			const response = await api.put(`/categories/${id}`, data);
			return response.data;
		},
		onSuccess: (_, variables) => {
			queryClient.invalidateQueries({ queryKey: categoryKeys.lists() });
			queryClient.invalidateQueries({ queryKey: categoryKeys.detail(variables.id) });
			toast.success("Category updated successfully");
		},
		onError: (error) => {
			toast.error("Failed to update category");
			console.error(error);
		},
	});
}

export function useDeleteCategory() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (id: string) => {
			const response = await api.delete(`/categories/${id}`);
			return response.data;
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: categoryKeys.lists() });
			toast.success("Category deleted successfully");
		},
		onError: (error) => {
			toast.error("Failed to delete category");
			console.error(error);
		},
	});
}
