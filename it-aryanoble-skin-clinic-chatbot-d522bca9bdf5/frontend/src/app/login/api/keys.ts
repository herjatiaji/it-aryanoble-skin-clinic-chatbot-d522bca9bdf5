export const authKeys = {
  all: ['auth'] as const,
  login: () => [...authKeys.all, 'login'] as const,
  me: () => [...authKeys.all, 'me'] as const,
};
