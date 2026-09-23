import { Skeleton } from "@/components/ui/skeleton";

export function MonthlyUsageSkeleton() {
	return (
		<div className="flex flex-col w-full">
			<div className="flex flex-col gap-6 border border-white-600 rounded-lg p-4 bg-white">
				<div className="flex flex-col gap-1">
					<Skeleton className="h-5 w-56 rounded" />
					<Skeleton className="h-4 w-96 rounded" />
				</div>
				<div className="flex items-center gap-6">
					<Skeleton className="size-17 rounded-full" />
					<div className="flex flex-col gap-2">
						<Skeleton className="h-4 w-40 rounded" />
						<Skeleton className="h-10 w-72 rounded-lg" />
					</div>
				</div>
			</div>
		</div>
	);
}
