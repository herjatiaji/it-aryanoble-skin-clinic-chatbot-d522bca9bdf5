import { DataTablePagination } from "@/components/shared/data-table-pagination";
import type { ChatHistoryResponse } from "../api/types";
import { ChatHistoryCard } from "./chat-history-card";
import { ChatHistoryEmptyState } from "./chat-history-empty-state";
import { ChatHistoryCardSkeleton } from "./skeletons/chat-history-card-skeleton";

interface ChatHistoryListProps {
	isLoading: boolean;
	isError: boolean;
	filteredData: ChatHistoryResponse[];
	paginatedItems: ChatHistoryResponse[];
	hasActiveFilters: boolean;
	onResetFilters: () => void;
	pagination: {
		page: number;
		pageSize: number;
		totalPages: number;
		totalItems: number;
		startIndex: number;
		endIndex: number;
		setPage: (page: number) => void;
		setPageSize: (size: number) => void;
	};
}

export function ChatHistoryList({
	isLoading,
	isError,
	filteredData,
	paginatedItems,
	hasActiveFilters,
	onResetFilters,
	pagination,
}: ChatHistoryListProps) {
	if (isLoading) {
		return <ChatHistoryCardSkeleton count={5} />;
	}

	if (isError) {
		return (
			<div className="p-4 text-sm text-red-500 bg-red-50 rounded-md">
				Failed to load chat history.
			</div>
		);
	}

	if (filteredData.length === 0) {
		return (
			<ChatHistoryEmptyState hasActiveFilters={hasActiveFilters} onResetFilters={onResetFilters} />
		);
	}

	return (
		<div className="flex flex-col gap-4">
			{paginatedItems.map((item) => (
				<ChatHistoryCard key={item.id} item={item} />
			))}

			<DataTablePagination
				page={pagination.page}
				pageSize={pagination.pageSize}
				totalPages={pagination.totalPages}
				totalItems={pagination.totalItems}
				startIndex={pagination.startIndex}
				endIndex={pagination.endIndex}
				onPageChange={pagination.setPage}
				onPageSizeChange={pagination.setPageSize}
				itemName="chat sessions"
			/>
		</div>
	);
}
