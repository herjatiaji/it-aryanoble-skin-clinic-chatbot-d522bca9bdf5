export const knowledgeKeys = {
  all: ["knowledge"] as const,
  lists: () => [...knowledgeKeys.all, "list"] as const,
  list: (filters: Record<string, unknown>) =>
    [...knowledgeKeys.lists(), filters] as const,
  details: () => [...knowledgeKeys.all, "detail"] as const,
  detail: (id: string) => [...knowledgeKeys.details(), id] as const,
};
