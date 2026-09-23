export const NOTIFICATION_KEYS = {
    all: ["feedbacks"] as const,
    lists: () => [...NOTIFICATION_KEYS.all, "list"] as const,
    detail: (id: string) => [...NOTIFICATION_KEYS.all, "detail", id] as const,
};
