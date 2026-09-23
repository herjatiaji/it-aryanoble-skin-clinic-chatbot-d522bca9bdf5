import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface ChatHistoryCardSkeletonProps {
	count?: number;
}

export function ChatHistoryCardSkeleton({ count = 5 }: ChatHistoryCardSkeletonProps) {
	return (
		<div className="flex flex-col gap-4">
			{Array.from({ length: count }).map((_, idx) => (
				<Card
					key={idx}
					className="p-4 flex flex-col gap-3 bg-white border border-gray-200 shadow-none"
				>
					{/* Session Query / Title */}
					<div className="space-y-1.5">
						<Skeleton className="h-4 w-3/4 rounded" />
					</div>

					{/* Meta items */}
					<div className="flex flex-wrap items-center gap-4 text-xs">
						<div className="flex items-center gap-1.5">
							<Skeleton className="size-3.5 rounded" />
							<Skeleton className="h-3 w-28 rounded" />
						</div>
						<div className="flex items-center gap-1.5">
							<Skeleton className="size-3.5 rounded" />
							<Skeleton className="h-3 w-6 rounded" />
						</div>
						<div className="flex items-center gap-1.5">
							<Skeleton className="size-4 rounded-full" />
							<Skeleton className="h-3 w-20 rounded" />
						</div>
						<div className="flex items-center gap-1.5">
							<Skeleton className="size-3.5 rounded" />
							<Skeleton className="h-3 w-24 rounded" />
						</div>
					</div>
				</Card>
			))}
		</div>
	);
}
