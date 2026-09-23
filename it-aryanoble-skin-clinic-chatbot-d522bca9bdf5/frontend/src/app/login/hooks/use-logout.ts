import { logoutApi } from "@/app/login/api";
import type { ApiError } from "@/lib/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";

export const useLogout = () => {
	const queryClient = useQueryClient();

	return useMutation<unknown, AxiosError<ApiError>, void>({
		mutationFn: async () => {
			if (typeof window !== "undefined") {
				sessionStorage.setItem("is_logging_out", "true");
				try {
					localStorage.removeItem("arya_noble_last_active");
				} catch {}
			}
			queryClient.cancelQueries();
			return await logoutApi();
		},
		onSuccess: () => {
			queryClient.clear();
			if (typeof window !== "undefined") {
				window.location.href = "/login";
			}
		},
		onError: () => {
			queryClient.clear();
			if (typeof window !== "undefined") {
				window.location.href = "/login";
			}
		},
	});
};
