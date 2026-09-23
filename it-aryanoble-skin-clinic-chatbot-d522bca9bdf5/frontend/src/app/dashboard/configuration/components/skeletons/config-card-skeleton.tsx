import { Skeleton } from "@/components/ui/skeleton";

interface ConfigCardSkeletonProps {
	lines?: number;
	className?: string;
}

export function ConfigCardSkeleton({ lines = 2, className = "" }: ConfigCardSkeletonProps) {
	return (
		<div
			className={`flex flex-col gap-4 border border-gray-100 rounded-lg p-4 bg-white animate-pulse ${className}`}
		>
			<div className="flex justify-between items-start">
				<div className="flex flex-col gap-2 w-full max-w-md">
					<Skeleton className="h-5 w-48 rounded" />
					<Skeleton className="h-3.5 w-80 rounded" />
				</div>
				<Skeleton className="h-9 w-20 rounded-md" />
			</div>
			{Array.from({ length: lines }).map((_, idx) => (
				<div
					key={idx}
					className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-3 rounded-lg border border-gray-100 bg-gray-50/50"
				>
					<div className="flex flex-col gap-1.5 w-full max-w-xs">
						<Skeleton className="h-4 w-36 rounded" />
						<Skeleton className="h-3 w-56 rounded" />
					</div>
					<Skeleton className="h-9 w-32 rounded-md" />
				</div>
			))}
		</div>
	);
}
