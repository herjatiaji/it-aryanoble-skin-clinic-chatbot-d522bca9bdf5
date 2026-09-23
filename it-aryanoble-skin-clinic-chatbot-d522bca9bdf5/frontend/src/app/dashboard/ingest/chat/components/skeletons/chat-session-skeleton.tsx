import { Skeleton } from "@/components/ui/skeleton";

export function ChatSessionSkeleton() {
	return (
		<div className="flex flex-col absolute inset-0 bg-white animate-pulse">
			{/* Header Skeleton */}
			<div className="flex items-center justify-between gap-4 px-4 py-3 border-b border-gray-200 shrink-0 bg-white">
				<div className="flex items-center gap-3">
					<Skeleton className="size-9 rounded-lg" />
					<Skeleton className="h-5 w-48 rounded" />
				</div>
				<Skeleton className="h-10 w-32 rounded-lg" />
			</div>

			{/* Chat Content Skeleton */}
			<div className="flex-1 p-6 space-y-6 overflow-hidden max-w-4xl mx-auto w-full">
				<div className="flex items-start gap-3">
					<Skeleton className="size-8 rounded-full shrink-0" />
					<div className="space-y-2 flex-1">
						<Skeleton className="h-4 w-1/4 rounded" />
						<Skeleton className="h-16 w-3/4 rounded-xl" />
					</div>
				</div>
				<div className="flex items-start gap-3 justify-end">
					<div className="space-y-2 flex-1 flex flex-col items-end">
						<Skeleton className="h-4 w-1/5 rounded" />
						<Skeleton className="h-12 w-2/3 rounded-xl" />
					</div>
					<Skeleton className="size-8 rounded-full shrink-0" />
				</div>
			</div>
		</div>
	);
}
