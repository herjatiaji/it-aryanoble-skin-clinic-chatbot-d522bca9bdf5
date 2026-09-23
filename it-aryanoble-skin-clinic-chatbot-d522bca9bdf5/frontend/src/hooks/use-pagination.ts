import { useState, useMemo } from "react";

export interface UsePaginationOptions<T> {
	items?: T[];
	totalItems?: number;
	initialPage?: number;
	initialPageSize?: number;
	onPageChange?: (page: number) => void;
	onPageSizeChange?: (pageSize: number) => void;
}

export interface UsePaginationReturn<T> {
	page: number;
	pageSize: number;
	totalPages: number;
	totalItems: number;
	paginatedItems: T[];
	setPage: (page: number) => void;
	setPageSize: (size: number) => void;
	nextPage: () => void;
	previousPage: () => void;
	canNextPage: boolean;
	canPreviousPage: boolean;
	startIndex: number;
	endIndex: number;
}

export function usePagination<T = unknown>({
	items,
	totalItems: explicitTotal,
	initialPage = 1,
	initialPageSize = 10,
	onPageChange,
	onPageSizeChange,
}: UsePaginationOptions<T> = {}): UsePaginationReturn<T> {
	const [pageState, setPageState] = useState(initialPage);
	const [pageSize, setPageSizeState] = useState(initialPageSize);

	const totalItems = explicitTotal ?? (items ? items.length : 0);
	const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

	// Derive safe page (clamp between 1 and totalPages)
	const page = Math.max(1, Math.min(pageState, totalPages));

	const setPage = (newPage: number) => {
		const targetPage = Math.max(1, Math.min(newPage, totalPages));
		setPageState(targetPage);
		onPageChange?.(targetPage);
	};

	const setPageSize = (newSize: number) => {
		setPageSizeState(newSize);
		setPageState(1);
		onPageSizeChange?.(newSize);
		onPageChange?.(1);
	};

	const nextPage = () => {
		if (page < totalPages) {
			setPage(page + 1);
		}
	};

	const previousPage = () => {
		if (page > 1) {
			setPage(page - 1);
		}
	};

	const paginatedItems = useMemo(() => {
		if (!items) return [];
		const start = (page - 1) * pageSize;
		return items.slice(start, start + pageSize);
	}, [items, page, pageSize]);

	const startIndex = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
	const endIndex = Math.min(page * pageSize, totalItems);

	return {
		page,
		pageSize,
		totalPages,
		totalItems,
		paginatedItems,
		setPage,
		setPageSize,
		nextPage,
		previousPage,
		canNextPage: page < totalPages,
		canPreviousPage: page > 1,
		startIndex,
		endIndex,
	};
}
