import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/axios";
import { getErrorMessage } from "@/lib/utils";
import { configKeys, branchKeys } from "../api/keys";
import { userKeys } from "@/app/dashboard/users/api/keys";
import type { ConfigResponse, ConfigUpdate, GlobalMonthlyUsageResponse } from "../api/types";

export const useConfigs = () => {
  return useQuery({
    queryKey: configKeys.lists(),
    queryFn: async (): Promise<ConfigResponse[]> => {
      const response = await api.get('/config/');
      return response.data;
    },
  });
};

export const useGlobalMonthlyUsage = () => {
  return useQuery({
    queryKey: configKeys.usage(),
    queryFn: async (): Promise<GlobalMonthlyUsageResponse> => {
      const response = await api.get('/config/usage');
      return response.data;
    },
  });
};

export const useUpdateConfig = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ key, data }: { key: string, data: ConfigUpdate }) => {
      const response = await api.put(`/config/${key}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: configKeys.all });
      queryClient.invalidateQueries({ queryKey: branchKeys.all });
      queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, "Failed to update settings."));
    }
  });
};

export const useValidateLLM = () => {
  return useMutation({
    mutationFn: async (data: { provider: string; model_name: string; api_key: string }) => {
      const response = await api.post(`/config/validate-llm`, data);
      return response.data;
    }
  });
};

export const useFetchModels = () => {
  return useMutation({
    mutationFn: async (data: { provider: string; api_key: string }) => {
      const response = await api.post<{ id: string; input_limit?: number; output_limit?: number }[]>(`/config/fetch-models`, data);
      return response.data;
    }
  });
};
