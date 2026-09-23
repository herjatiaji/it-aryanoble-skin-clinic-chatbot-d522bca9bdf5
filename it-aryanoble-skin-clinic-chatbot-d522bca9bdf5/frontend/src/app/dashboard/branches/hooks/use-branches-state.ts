"use client";

import { useConfigs } from "@/app/dashboard/configuration/hooks/use-config";
import { useDebounce } from "@/hooks/use-debounce";
import { usePagination } from "@/hooks/use-pagination";
import { useTableSort } from "@/hooks/use-table-sort";
import { useMemo, useState } from "react";
import { BranchResponse } from "../api/types";
import { useBranches } from "./use-branches";

export function useBranchesState() {
	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 300);

	const { data: branches = [], isLoading } = useBranches();
	const { data: configs } = useConfigs();

	const isMasterActive =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT_ACTIVE")?.value === "true";
	const isBranchGlobalActive =
		configs?.find((c) => c.key === "GLOBAL_BRANCH_LIMIT_ACTIVE")?.value === "true";
	const isGlobalLimitActive = isMasterActive && isBranchGlobalActive;

	const globalBranchLimit =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT")?.value || "3000000";

	const { sortKey, sortOrder, handleSort, sortItems } = useTableSort({
		initialSortKey: "name",
		initialSortOrder: "asc",
	});

	const filteredBranches = useMemo(() => {
		if (!branches) return [];
		let result = branches;
		if (debouncedSearch.trim()) {
			const q = debouncedSearch.toLowerCase();
			result = branches.filter(
				(branch) =>
					branch.name?.toLowerCase().includes(q) ||
					branch.code?.toLowerCase().includes(q) ||
					branch.ecosystem?.toLowerCase().includes(q),
			);
		}
		return sortItems<BranchResponse>(result, (branch: BranchResponse, key: string) => {
			const hasCustomLimit = branch.has_custom_limit ?? false;
			const effectiveLimit = hasCustomLimit
				? (branch.token_limit ?? 0)
				: isGlobalLimitActive
				? Number(globalBranchLimit)
				: (branch.token_limit ?? branch.tokensMonth ?? 0);
			const used = branch.used ?? 0;
			if (key === "remaining") return branch.remaining ?? Math.max(0, effectiveLimit - used);
			if (key === "token_limit") return effectiveLimit;
			if (key === "used") return used;
			return (branch as unknown as Record<string, unknown>)[key];
		});
	}, [branches, debouncedSearch, sortItems, isGlobalLimitActive, globalBranchLimit]);

	const pagination = usePagination<BranchResponse>({
		items: filteredBranches,
		initialPageSize: 10,
	});

	const handleClearSearch = () => {
		setSearchQuery("");
	};

	return {
		searchQuery,
		setSearchQuery,
		handleClearSearch,
		isLoading,
		hasFilter: Boolean(debouncedSearch.trim()),
		isGlobalLimitActive,
		globalBranchLimit,
		filteredBranches,
		pagination,
		sortKey,
		sortOrder,
		handleSort,
	};
}
