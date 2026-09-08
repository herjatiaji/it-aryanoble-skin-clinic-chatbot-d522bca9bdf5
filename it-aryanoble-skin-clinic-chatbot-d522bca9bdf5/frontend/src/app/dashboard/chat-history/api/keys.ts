export const chatHistoryKeys = {
  all: ["chat-history"] as const,
  lists: () => [...chatHistoryKeys.all, "list"] as const,
  list: (filters: Record<string, unknown>) =>
    [...chatHistoryKeys.lists(), filters] as const,
  details: () => [...chatHistoryKeys.all, "detail"] as const,
  detail: (id: string) => [...chatHistoryKeys.details(), id] as const,
};
