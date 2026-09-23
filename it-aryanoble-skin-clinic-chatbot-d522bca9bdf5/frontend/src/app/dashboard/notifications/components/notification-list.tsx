import { DataTablePagination } from "@/components/shared/data-table-pagination";
import { usePagination } from "@/hooks/use-pagination";
import { FeedbackNotification } from "../api/types";
import { NotificationFilterTab } from "../hooks/use-notifications-state";
import { NotificationEmptyState } from "./notification-empty-state";
import { NotificationItem } from "./notification-item";
import { NotificationListSkeleton } from "./skeletons/notification-list-skeleton";

interface NotificationListProps {
	isLoading: boolean;
	totalFilteredCount: number;
	hasActiveFilters: boolean;
	activeTab: NotificationFilterTab;
	onMarkAsRead: (id: string) => void;
	pagination: ReturnType<typeof usePagination<FeedbackNotification>>;
}

export function NotificationList({
	isLoading,
	totalFilteredCount,
	hasActiveFilters,
	activeTab,
	onMarkAsRead,
	pagination,
}: NotificationListProps) {
	return (
		<div className="flex-1 overflow-y-auto">
			{isLoading ? (
				<NotificationListSkeleton />
			) : totalFilteredCount === 0 ? (
				<NotificationEmptyState hasActiveFilters={hasActiveFilters} activeTab={activeTab} />
			) : (
				<div className="flex flex-col gap-2.5">
					{pagination.paginatedItems.map((item) => (
						<NotificationItem key={item.id} item={item} onMarkAsRead={onMarkAsRead} />
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
						itemName="notifications"
					/>
				</div>
			)}
		</div>
	);
}
