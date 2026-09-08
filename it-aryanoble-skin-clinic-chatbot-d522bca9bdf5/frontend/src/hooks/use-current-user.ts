import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/axios";
import type { UserResponse } from "@/lib/types";

import { authKeys } from "@/app/login/api/keys";

export const useCurrentUser = () => {
  return useQuery({
    queryKey: authKeys.me(),
    queryFn: async (): Promise<UserResponse> => {
      const response = await api.get("/users/me");
      return response.data;
    },
    retry: 0, // Don't retry if it fails (e.g., 401 Unauthorized)
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });
};
