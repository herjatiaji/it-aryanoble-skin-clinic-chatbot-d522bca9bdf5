import { MessageScrollerItem } from "@/components/ui/message-scroller";
import { Skeleton } from "@/components/ui/skeleton";
import { RiRobot2Line, RiUser3Line } from "@remixicon/react";

export function ChatDetailSkeleton() {
	return (
		<>
			{/* User Question Bubble Skeleton */}
			<MessageScrollerItem>
				<div className="flex flex-col w-full min-w-0 max-w-full items-end">
					<div className="flex items-start gap-3 w-full min-w-0 max-w-full flex-row-reverse">
						<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
							<RiUser3Line className="size-4 text-zinc-400" />
						</div>
						<div className="bg-blue-50/70 border border-blue-100/50 p-3.5 rounded-md w-full max-w-[65%] space-y-2">
							<Skeleton className="h-4 w-3/4 rounded" />
							<Skeleton className="h-4 w-1/2 rounded" />
						</div>
					</div>
				</div>
			</MessageScrollerItem>

			{/* Assistant Response Bubble Skeleton */}
			<MessageScrollerItem>
				<div className="flex flex-col w-full min-w-0 max-w-full items-start">
					<div className="flex items-start gap-3 w-full min-w-0 max-w-full">
						<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
							<RiRobot2Line className="size-4 animate-pulse text-blue-500" />
						</div>
						<div className="border border-zinc-200 p-3.5 rounded-md w-full space-y-3">
							<Skeleton className="h-4 w-full rounded" />
							<Skeleton className="h-4 w-5/6 rounded" />
							<Skeleton className="h-4 w-2/3 rounded" />
							<div className="pt-2 flex gap-2">
								<Skeleton className="h-5 w-24 rounded-md" />
								<Skeleton className="h-5 w-20 rounded-md" />
							</div>
						</div>
					</div>
				</div>
			</MessageScrollerItem>
		</>
	);
}
