"use client";

import type { SortOrder } from "@/components/shared/sortable-table-head";
import { useCallback, useState } from "react";

export interface UseTableSortOptions {
	initialSortKey?: string | null;
	initialSortOrder?: SortOrder;
}

export function useTableSort({
	initialSortKey = null,
	initialSortOrder = null,
}: UseTableSortOptions = {}) {
	const [sortKey, setSortKey] = useState<string | null>(initialSortKey);
	const [sortOrder, setSortOrder] = useState<SortOrder>(initialSortOrder);

	const handleSort = useCallback((key: string) => {
		setSortKey((prevKey) => {
			if (prevKey === key) {
				setSortOrder((prevOrder) => {
					if (prevOrder === "asc") return "desc";
					if (prevOrder === "desc") return null;
					return "asc";
				});
				return key;
			}
			setSortOrder("asc");
			return key;
		});
	}, []);

	const resetSort = useCallback(() => {
		setSortKey(initialSortKey);
		setSortOrder(initialSortOrder);
	}, [initialSortKey, initialSortOrder]);

	const sortItems = useCallback(
		<T>(items: T[], getValue?: (item: T, key: string) => unknown): T[] => {
			if (!sortKey || !sortOrder || !items.length) {
				return items;
			}

			return [...items].sort((a, b) => {
				const valA = getValue ? getValue(a, sortKey) : (a as Record<string, unknown>)[sortKey];
				const valB = getValue ? getValue(b, sortKey) : (b as Record<string, unknown>)[sortKey];

				if (valA === valB) return 0;
				if (valA === null || valA === undefined) return 1;
				if (valB === null || valB === undefined) return -1;

				if (typeof valA === "number" && typeof valB === "number") {
					return sortOrder === "asc" ? valA - valB : valB - valA;
				}

				if (typeof valA === "string" && typeof valB === "string") {
					// Check if valid date string
					const isDateA = !isNaN(Date.parse(valA)) && (valA.includes("-") || valA.includes("T"));
					const isDateB = !isNaN(Date.parse(valB)) && (valB.includes("-") || valB.includes("T"));

					if (isDateA && isDateB) {
						const timeA = new Date(valA).getTime();
						const timeB = new Date(valB).getTime();
						return sortOrder === "asc" ? timeA - timeB : timeB - timeA;
					}

					return sortOrder === "asc"
						? valA.localeCompare(valB, undefined, { numeric: true, sensitivity: "base" })
						: valB.localeCompare(valA, undefined, { numeric: true, sensitivity: "base" });
				}

				// Fallback
				const strA = String(valA);
				const strB = String(valB);
				return sortOrder === "asc"
					? strA.localeCompare(strB, undefined, { numeric: true, sensitivity: "base" })
					: strB.localeCompare(strA, undefined, { numeric: true, sensitivity: "base" });
			});
		},
		[sortKey, sortOrder],
	);

	return {
		sortKey,
		sortOrder,
		handleSort,
		resetSort,
		sortItems,
		setSortKey,
		setSortOrder,
	};
}
