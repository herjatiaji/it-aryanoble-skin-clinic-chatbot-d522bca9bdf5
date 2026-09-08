import { RiNotification3Line, RiCheckDoubleLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";

export default function NotificationsPage() {
	return (
		<div className="flex flex-col h-full gap-6 p-6">
			<div className="flex items-center justify-between">
                <div className="flex flex-col gap-1">
                    <h1 className="text-xl font-semibold text-foreground">Notifications</h1>
                    <p className="text-sm text-muted-foreground">
                        Review feedback and reports submitted by doctors during chat sessions.
                    </p>
                </div>
                <Button variant="outline" size="sm" className="h-9">
                    <RiCheckDoubleLine className="size-4 mr-2" />
                    Mark all as read
                </Button>
			</div>

			<div className="border border-gray-100 rounded-md bg-white overflow-hidden flex-1 flex flex-col">
				<div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
					<div className="bg-gray-50 h-16 w-16 rounded-full flex items-center justify-center mb-4">
						<RiNotification3Line className="size-8 text-gray-400" />
					</div>
					<h3 className="text-sm font-medium text-gray-900">No notifications</h3>
					<p className="text-sm text-gray-500 mt-1">You&apos;re all caught up! Check back later.</p>
				</div>
			</div>
		</div>
    );
}
