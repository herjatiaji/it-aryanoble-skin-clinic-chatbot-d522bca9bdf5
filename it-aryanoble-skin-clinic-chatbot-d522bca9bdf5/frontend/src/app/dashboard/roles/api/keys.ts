export const roleKeys = {
	all: ["roles"] as const,
	lists: () => [...roleKeys.all, "list"] as const,
	detail: (id: string) => [...roleKeys.all, "detail", id] as const,
	accesses: () => [...roleKeys.all, "accesses"] as const,
};

export const userKeys = {
	all: ["users"] as const,
	lists: () => [...userKeys.all, "list"] as const,
};
