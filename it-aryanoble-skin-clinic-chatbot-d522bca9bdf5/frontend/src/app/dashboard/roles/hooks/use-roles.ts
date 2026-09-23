import { api } from "@/lib/axios";
import { getErrorMessage } from "@/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { roleKeys, userKeys } from "../api/keys";
import type {
	AccessResponse,
	RoleCreatePayload,
	RoleDetailResponse,
	RoleUpdatePayload,
} from "../api/types";

export const useRoles = () => {
	return useQuery({
		queryKey: roleKeys.lists(),
		queryFn: async (): Promise<RoleDetailResponse[]> => {
			const response = await api.get("/roles/");
			return response.data;
		},
	});
};

export const useAvailableAccesses = () => {
	return useQuery({
		queryKey: roleKeys.accesses(),
		queryFn: async (): Promise<AccessResponse[]> => {
			const response = await api.get("/roles/accesses");
			return response.data;
		},
	});
};

export const useCreateRole = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (payload: RoleCreatePayload) => {
			const response = await api.post("/roles/", payload);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Role created successfully!");
			queryClient.invalidateQueries({ queryKey: roleKeys.all, refetchType: "all" });
			queryClient.invalidateQueries({ queryKey: userKeys.all, refetchType: "all" });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to create role."));
		},
	});
};

export const useUpdateRole = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ roleId, data }: { roleId: string; data: RoleUpdatePayload }) => {
			const response = await api.put(`/roles/${roleId}`, data);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Role updated successfully!");
			queryClient.invalidateQueries({ queryKey: roleKeys.all, refetchType: "all" });
			queryClient.invalidateQueries({ queryKey: userKeys.all, refetchType: "all" });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to update role."));
		},
	});
};

export const useDeleteRole = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (roleId: string) => {
			const response = await api.delete(`/roles/${roleId}`);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Role deleted successfully!");
			queryClient.invalidateQueries({ queryKey: roleKeys.all, refetchType: "all" });
			queryClient.invalidateQueries({ queryKey: userKeys.all, refetchType: "all" });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to delete role."));
		},
	});
};
