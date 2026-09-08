import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { api } from "@/lib/axios";
import { useRouter } from "next/navigation";
import { authKeys } from "../api/keys";
import type { ApiError } from "@/lib/types";

export const useLogout = () => {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation<unknown, AxiosError<ApiError>, void>({
    mutationFn: async () => {
      const response = await api.post('/auth/logout');
      return response.data;
    },
    onSuccess: () => {
      // Clear any user-related cache
      queryClient.removeQueries({ queryKey: authKeys.all });
      // Redirect to login page
      router.push("/login");
    },
  });
};
