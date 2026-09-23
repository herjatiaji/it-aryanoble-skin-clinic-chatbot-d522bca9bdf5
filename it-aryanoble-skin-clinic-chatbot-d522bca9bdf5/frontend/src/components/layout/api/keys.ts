export const searchKeys = {
	all: ["search"] as const,
	global: (query: string, category?: string, limit?: number) =>
		[...searchKeys.all, "global", { query, category, limit }] as const,
};
