import { RiNotification3Line } from "@remixicon/react";
import { NotificationFilterTab } from "../hooks/use-notifications-state";

interface NotificationEmptyStateProps {
	hasActiveFilters: boolean;
	activeTab: NotificationFilterTab;
}

export function NotificationEmptyState({
	hasActiveFilters,
	activeTab,
}: NotificationEmptyStateProps) {
	return (
		<div className="bg-white border border-gray-200 rounded-lg flex flex-col items-center justify-center p-10 text-center">
			<div className="bg-gray-50 size-10 rounded-full flex items-center justify-center mb-2.5 text-muted-foreground">
				<RiNotification3Line className="size-5 text-gray-400" />
			</div>
			<h3 className="text-xs font-medium text-gray-900">
				{hasActiveFilters
					? "No matching notifications"
					: activeTab === "unread"
						? "No unread notifications"
						: activeTab === "read"
							? "No read notifications"
							: "No notifications"}
			</h3>
			<p className="text-[11px] text-muted-foreground mt-0.5 max-w-xs">
				{hasActiveFilters
					? "Try changing your search keywords or resetting active filters."
					: activeTab === "unread"
						? "You are caught up with all reported data issues."
						: activeTab === "read"
							? "No read notifications found."
							: "Reported missing data issues from doctors will appear here."}
			</p>
		</div>
	);
}
