import { api } from "@/lib/axios";
import type { UserResponse } from "@/lib/types";
import type { LoginResponse } from "./types";

export const loginApi = async (credentials: URLSearchParams): Promise<{ loginResponse: LoginResponse; userProfile: UserResponse }> => {
	const loginRes = await api.post<LoginResponse>("/auth/login", credentials, {
		headers: {
			"Content-Type": "application/x-www-form-urlencoded",
		},
	});

	const meRes = await api.get<UserResponse>("/users/me");

	return {
		loginResponse: loginRes.data,
		userProfile: meRes.data,
	};
};

export const logoutApi = async (): Promise<unknown> => {
	const response = await api.post("/auth/logout");
	return response.data;
};

export const fetchMeApi = async (): Promise<UserResponse> => {
	const response = await api.get<UserResponse>("/users/me");
	return response.data;
};

export * from "./keys";
export * from "./types";
