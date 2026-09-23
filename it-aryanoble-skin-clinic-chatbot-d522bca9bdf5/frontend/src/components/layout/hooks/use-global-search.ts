"use client";

import { useDebounce } from "@/hooks/use-debounce";
import { useQuery } from "@tanstack/react-query";
import { searchGlobal, searchKeys, type UnifiedSearchResponse } from "../api";

export { useDebounce };

export function useGlobalSearch(
	query: string,
	category: "all" | "knowledge" | "projects" | "categories" | "chats" = "all",
	debounceMs: number = 200,
) {
	const debouncedQuery = useDebounce(query, debounceMs);

	const queryResult = useQuery<UnifiedSearchResponse>({
		queryKey: searchKeys.global(debouncedQuery, category),
		queryFn: () => searchGlobal(debouncedQuery, category),
		enabled: debouncedQuery.trim().length > 0,
		staleTime: 1000 * 30,
	});

	return {
		...queryResult,
		isDebouncing: query !== debouncedQuery,
		debouncedQuery,
	};
}
