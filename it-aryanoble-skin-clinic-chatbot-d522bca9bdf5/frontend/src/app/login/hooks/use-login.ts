import { authKeys, loginApi, type LoginResponse } from "@/app/login/api";
import type { ApiError, UserResponse } from "@/lib/types";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";

export const useLogin = () => {
	const queryClient = useQueryClient();

	return useMutation<
		{ loginResponse: LoginResponse; userProfile: UserResponse },
		AxiosError<ApiError>,
		URLSearchParams
	>({
		mutationFn: (credentials) => loginApi(credentials),
		onSuccess: (data) => {
			if (typeof window !== "undefined") {
				try {
					localStorage.setItem("arya_noble_last_active", Date.now().toString());
				} catch {}
			}
			queryClient.setQueryData(authKeys.me(), data.userProfile);
		},
	});
};
