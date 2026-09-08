# Frontend & Backend Integration Guide

This document outlines the strict standards for integrating the Next.js frontend with the FastAPI backend in the Arya Noble project. Following these rules ensures complete type safety, predictable cache invalidation, and a scalable architecture.

## 1. Feature-Based Architecture

All API-related files (types and hooks) must be colocated with the feature or page that uses them. Do not dump all hooks into a global `src/hooks` folder.

**Example Structure:**
```
src/
└── app/
    └── admin/
        └── users/
            ├── page.tsx
            ├── components/
            │   └── user-table.tsx
            ├── api/
            │   ├── types.ts          # TypeScript interfaces mirroring Backend schemas
            │   └── keys.ts           # Query Key Factory for users
            └── hooks/
                └── use-users.ts      # React Query custom hooks
```

## 2. Type Safety Strategy

Always manually mirror the backend Pydantic models (from `app/schemas/`) into TypeScript interfaces in `types.ts`. 

```typescript
// src/app/admin/users/api/types.ts
export interface UserResponse {
  id: string;
  name: string;
  email: string;
  type: "ADMIN" | "DOCTOR" | "STAFF";
  status: "Active" | "Inactive" | "Warning";
  // ... other fields exactly matching Pydantic
}
```

## 3. Query Key Factories

Never inline strings for React Query keys (e.g., `useQuery({ queryKey: ['users'] })`). Always use a centralized Query Key Factory in `keys.ts` to prevent typos and ensure cache invalidation works globally.

```typescript
// src/app/admin/users/api/keys.ts
export const userKeys = {
  all: ['users'] as const,
  lists: () => [...userKeys.all, 'list'] as const,
  list: (filters: string) => [...userKeys.lists(), { filters }] as const,
  details: () => [...userKeys.all, 'detail'] as const,
  detail: (id: string) => [...userKeys.details(), id] as const,
};
```

## 4. Writing React Query Hooks

Use the pre-configured Axios instance (`@/lib/axios`) for all requests. Encapsulate the data fetching logic directly inside custom hooks in `use-<feature>.ts`.

```typescript
// src/app/admin/users/hooks/use-users.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/axios";
import { getErrorMessage } from "@/lib/utils";
import { userKeys } from "../api/keys";
import type { UserResponse } from "../api/types";

// GET Hook
export const useUsers = () => {
  return useQuery({
    queryKey: userKeys.lists(),
    queryFn: async (): Promise<UserResponse[]> => {
      const response = await api.get('/users/');
      return response.data;
    },
  });
};

// POST Hook with Invalidations & Toasts
export const useCreateUser = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (newUser) => {
      const response = await api.post('/users/', newUser);
      return response.data;
    },
    onSuccess: () => {
      toast.success("User created successfully!");
      // Invalidate the list to trigger a refetch
      queryClient.invalidateQueries({ queryKey: userKeys.lists() });
    },
    onError: (error: any) => {
      toast.error(getErrorMessage(error, "Failed to create user."));
    }
  });
};
```

## 5. Error Typings & Loading States

### API Errors & Toasts
Always use the standardized `getErrorMessage` utility from `src/lib/utils.ts` to parse FastAPI error arrays and strings consistently.
Additionally, you **MUST** use toast notifications (e.g., `sonner`) within your hooks' or components' `onSuccess` and `onError` callbacks for mutations to ensure the user is always notified of the result. Avoid relying solely on inline form errors unless explicitly required by the design.

```typescript
import { getErrorMessage } from "@/lib/utils";

// Inside your mutation's onError:
onError: (error: any) => {
  toast.error(getErrorMessage(error, "Custom fallback message"));
}
```

### Loading States
When consuming custom hooks, leverage the `isLoading` and `isPending` states provided by React Query. Render skeleton loaders matching the target UI when data is loading rather than basic spinners.

## 6. Non-API Hooks & Zod Schemas

For features that require custom state management (non-API hooks) or form validation schemas (Zod):
- **Non-API Custom Hooks**: Global utility hooks should be placed in `src/hooks/`. Feature-specific hooks (e.g., complex UI state for a specific page) should be colocated in `src/app/<feature>/hooks/`.
- **Zod Schemas**: Colocate Zod schemas with the feature components they belong to (e.g., `src/app/<feature>/components/<name>-schema.ts`).

## Summary Checklist
- [ ] Are my types in `api/types.ts` perfectly matching the FastAPI schemas?
- [ ] Am I using the `api` instance from `@/lib/axios`?
- [ ] Have I defined my query keys in `api/keys.ts` using a factory pattern?
- [ ] Is my custom hook colocated in the feature folder?
- [ ] Are my feature-specific Zod schemas and non-API hooks properly colocated?
