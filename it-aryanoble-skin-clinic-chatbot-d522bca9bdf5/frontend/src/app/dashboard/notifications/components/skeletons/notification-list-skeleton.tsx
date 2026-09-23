import { Skeleton } from "@/components/ui/skeleton";

interface NotificationListSkeletonProps {
	count?: number;
}

export function NotificationListSkeleton({ count = 4 }: NotificationListSkeletonProps) {
	return (
		<div className="flex flex-col gap-2.5">
			{[...Array(count)].map((_, i) => (
				<div
					key={i}
					className="bg-white border border-gray-200 rounded-lg p-3.5 sm:p-4 flex flex-col gap-3"
				>
					{/* Header Row */}
					<div className="flex items-center justify-between gap-2.5">
						<div className="flex items-center gap-2">
							<Skeleton className="size-1.5 rounded-full" />
							<Skeleton className="h-4 w-32" />
							<Skeleton className="h-4 w-20 rounded-md" />
							<Skeleton className="h-4 w-24 rounded-md" />
						</div>
						<Skeleton className="h-3.5 w-28" />
					</div>

					{/* Feedback Content Box */}
					<div className="bg-gray-50 border border-gray-200/70 rounded-md p-2.5 space-y-1.5">
						<Skeleton className="h-3 w-20" />
						<Skeleton className="h-3.5 w-full" />
						<Skeleton className="h-3.5 w-3/4" />
					</div>

					{/* Footer Row */}
					<div className="flex items-center justify-between gap-2.5 pt-1 border-t border-gray-100">
						<Skeleton className="h-6 w-24 rounded-md" />
						<div className="flex items-center gap-2">
							<Skeleton className="h-8 w-20 rounded-lg" />
							<Skeleton className="h-8 w-32 rounded-lg" />
						</div>
					</div>
				</div>
			))}
		</div>
	);
}
