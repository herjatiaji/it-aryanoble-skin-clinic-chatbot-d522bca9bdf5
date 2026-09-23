export const knowledgeKeys = {
  all: ["knowledge"] as const,
  lists: () => [...knowledgeKeys.all, "list"] as const,
  list: (filters: Record<string, unknown>) =>
    [...knowledgeKeys.lists(), filters] as const,
  details: () => [...knowledgeKeys.all, "detail"] as const,
  detail: (id: string) => [...knowledgeKeys.details(), id] as const,
};

export const projectKeys = {
  all: ["projects"] as const,
  lists: () => [...projectKeys.all, "list"] as const,
  list: (filters: Record<string, unknown>) =>
    [...projectKeys.lists(), filters] as const,
  details: () => [...projectKeys.all, "detail"] as const,
  detail: (id: string) => [...projectKeys.details(), id] as const,
  stats: () => [...projectKeys.all, "stats"] as const,
};
