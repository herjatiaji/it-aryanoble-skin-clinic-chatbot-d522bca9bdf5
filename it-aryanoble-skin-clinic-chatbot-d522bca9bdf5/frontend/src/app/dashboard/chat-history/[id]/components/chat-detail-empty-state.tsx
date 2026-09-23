import { MessageScrollerItem } from "@/components/ui/message-scroller";
import { RiRobot2Line } from "@remixicon/react";

export function ChatDetailEmptyState() {
	return (
		<MessageScrollerItem>
			<div className="flex flex-col items-center justify-center text-center py-16 px-4 max-w-lg mx-auto space-y-3">
				<div className="size-12 rounded-xl bg-blue-50 text-blue-500 flex items-center justify-center">
					<RiRobot2Line className="size-6" />
				</div>
				<h2 className="text-base font-semibold text-zinc-950">No Messages</h2>
				<p className="text-xs text-zinc-500 leading-relaxed">
					There are no messages recorded for this conversation session.
				</p>
			</div>
		</MessageScrollerItem>
	);
}
