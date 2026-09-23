import { Skeleton } from "@/components/ui/skeleton";

export function LoginFormSkeleton() {
	return (
		<div className="flex flex-col gap-6 animate-pulse">
			{/* Header */}
			<div className="flex flex-col items-center text-center">
				<Skeleton className="mb-4 h-12 w-12 rounded-lg" />
				<Skeleton className="mb-1 h-6 w-48 rounded" />
				<div className="flex flex-col items-center gap-1.5 pt-1">
					<Skeleton className="h-3.5 w-72 rounded" />
					<Skeleton className="h-3.5 w-56 rounded" />
				</div>
			</div>

			<div className="space-y-4">
				{/* Email Field */}
				<div className="space-y-2">
					<Skeleton className="h-4 w-12 rounded" />
					<Skeleton className="h-9 w-full rounded-md" />
				</div>

				{/* Password Field */}
				<div className="space-y-2">
					<Skeleton className="h-4 w-16 rounded" />
					<Skeleton className="h-9 w-full rounded-md" />
				</div>

				{/* Submit Button */}
				<div className="pt-2">
					<Skeleton className="h-10 w-full rounded-lg" />
				</div>
			</div>
		</div>
	);
}
