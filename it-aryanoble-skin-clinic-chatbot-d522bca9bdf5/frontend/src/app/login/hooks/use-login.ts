import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { api } from "@/lib/axios";
import type { LoginResponse } from "../api/types";
import type { ApiError, UserResponse } from "@/lib/types";
import { authKeys } from "../api/keys";

export const useLogin = () => {
  const queryClient = useQueryClient();

  return useMutation<
    { loginResponse: LoginResponse, userProfile: UserResponse },
    AxiosError<ApiError>,
    URLSearchParams
  >({
    mutationFn: async (credentials) => {
      // 1. Perform login
      const loginRes = await api.post<LoginResponse>('/auth/login', credentials, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      // 2. Fetch user profile
      const meRes = await api.get<UserResponse>('/users/me');
      
      return {
        loginResponse: loginRes.data,
        userProfile: meRes.data,
      };
    },
    onSuccess: (data) => {
      queryClient.setQueryData(authKeys.me(), data.userProfile);
    },
  });
};
