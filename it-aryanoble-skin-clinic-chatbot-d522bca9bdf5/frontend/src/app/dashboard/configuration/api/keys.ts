export const configKeys = {
  all: ['configs'] as const,
  lists: () => [...configKeys.all, 'list'] as const,
  detail: (key: string) => [...configKeys.all, 'detail', key] as const,
};

export const branchKeys = {
  all: ['branches'] as const,
  lists: () => [...branchKeys.all, 'list'] as const,
  detail: (id: string) => [...branchKeys.all, 'detail', id] as const,
};
