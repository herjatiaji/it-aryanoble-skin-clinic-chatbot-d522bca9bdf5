import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/axios";
import type { UserResponse } from "@/lib/types";

import { authKeys } from "@/app/login/api/keys";
import { AxiosError } from "axios";

export const useCurrentUser = () => {
  return useQuery({
    queryKey: authKeys.me(),
    queryFn: async (): Promise<UserResponse> => {
      const response = await api.get("/users/me");
      return response.data;
    },
    retry: (failureCount, error) => {
      if (error instanceof AxiosError && error.response) {
        if (error.response.status === 401 || error.response.status === 403) {
          return false;
        }
      }
      return failureCount < 2;
    },
    retryDelay: 1000,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });
};
