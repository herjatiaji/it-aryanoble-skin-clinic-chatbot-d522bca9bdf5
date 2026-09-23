"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // Initialize QueryClient once per session in a useState to ensure it's not recreated on every render
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 1000, // 5 seconds - keeps UI fast while ensuring route transitions fetch fresh data
            refetchOnMount: true, // Always re-check and fetch latest state when mounting a page/component
            refetchOnWindowFocus: false, // Don't automatically refetch when switching OS windows
            retry: 1, // Only retry once on failure
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
