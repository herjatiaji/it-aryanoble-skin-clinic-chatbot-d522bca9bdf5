import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RiCheckDoubleLine } from "@remixicon/react";

interface NotificationHeaderProps {
	unreadCount: number;
	isMarkingRead: boolean;
	onMarkAllAsRead: () => void;
}

export function NotificationHeader({
	unreadCount,
	isMarkingRead,
	onMarkAllAsRead,
}: NotificationHeaderProps) {
	return (
		<div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
			<div className="flex flex-col gap-1">
				<div className="flex items-center gap-2">
					<h1 className="text-xl font-semibold text-foreground">Notifications</h1>
					{unreadCount > 0 && (
						<Badge
							variant="secondary"
							className="bg-amber-50 text-amber-800 border-amber-200 text-[11px] font-semibold px-1.5 py-0"
						>
							{unreadCount} unread
						</Badge>
					)}
				</div>
				<p className="text-sm text-muted-foreground">
					Reported missing data issues and doctor feedback across chat sessions.
				</p>
			</div>

			<Button
				variant="outline"
				className="h-9 px-3 text-xs sm:text-sm border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg font-medium self-start sm:self-auto shadow-none cursor-pointer gap-1.5"
				onClick={onMarkAllAsRead}
				disabled={unreadCount === 0 || isMarkingRead}
			>
				<RiCheckDoubleLine className="size-3.5 text-zinc-500" />
				Mark all as read
			</Button>
		</div>
	);
}
