import { Skeleton } from "@/components/ui/skeleton";

export function IngestSkeleton() {
	return (
		<div className="flex flex-col max-w-2xl mx-auto min-h-full w-full pt-10 pb-10 px-4 animate-pulse">
			{/* Header Skeleton */}
			<div className="flex flex-col items-center text-center space-y-2 mb-8">
				<Skeleton className="size-12 rounded-md" />
				<div className="space-y-1 flex flex-col items-center">
					<Skeleton className="h-6 w-48 rounded" />
					<Skeleton className="h-4 w-80 max-w-full rounded" />
				</div>
			</div>

			{/* Shortcuts Skeleton */}
			<div className="grid grid-cols-2 gap-3 w-full mb-4 shrink-0">
				<div className="flex flex-col items-start p-3 rounded-lg border border-zinc-200/70 bg-white space-y-2">
					<Skeleton className="size-4 rounded" />
					<Skeleton className="h-3.5 w-32 rounded" />
					<Skeleton className="h-3 w-full rounded" />
				</div>
				<div className="flex flex-col items-start p-3 rounded-lg border border-zinc-200/70 bg-white space-y-2">
					<Skeleton className="size-4 rounded" />
					<Skeleton className="h-3.5 w-32 rounded" />
					<Skeleton className="h-3 w-full rounded" />
				</div>
			</div>

			{/* Prompt Input Skeleton */}
			<div className="shrink-0 mt-4 flex flex-col items-center relative">
				<div className="w-full rounded-lg p-3 border border-zinc-200/80 bg-zinc-50/50 space-y-3">
					<div className="space-y-2 py-2">
						<Skeleton className="h-4 w-3/4 rounded" />
						<Skeleton className="h-4 w-1/2 rounded" />
						<Skeleton className="h-4 w-2/3 rounded" />
					</div>
					<div className="flex items-center justify-between pt-2">
						<Skeleton className="h-7 w-20 rounded-md" />
						<Skeleton className="size-8 rounded-lg" />
					</div>
				</div>

				{/* Mode Controls Skeleton */}
				<div className="w-full flex items-center justify-between gap-3 mt-3 px-0.5">
					<div className="flex items-center gap-2.5">
						<Skeleton className="h-4 w-12 rounded" />
						<Skeleton className="h-5 w-9 rounded-full" />
						<Skeleton className="h-4 w-16 rounded" />
					</div>
					<Skeleton className="h-7 w-28 rounded-md" />
				</div>

				{/* File Format Badge Skeleton */}
				<Skeleton className="h-6 w-64 rounded-full mt-4 mx-auto" />
			</div>
		</div>
	);
}
