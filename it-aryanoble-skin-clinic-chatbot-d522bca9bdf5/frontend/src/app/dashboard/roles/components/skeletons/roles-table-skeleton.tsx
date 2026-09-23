import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";

interface RolesTableSkeletonProps {
	rows?: number;
}

export function RolesTableSkeleton({ rows = 5 }: RolesTableSkeletonProps) {
	return (
		<>
			{Array.from({ length: rows }).map((_, rIdx) => (
				<TableRow key={rIdx} className="hover:bg-transparent border-gray-100">
					{/* Role Name */}
					<TableCell className="w-[30%] py-4">
						<div className="flex items-center gap-2">
							<Skeleton className="h-4 w-32 rounded" />
							{rIdx === 0 && (
								<Skeleton className="h-4 w-12 rounded bg-purple-100" />
							)}
						</div>
					</TableCell>

					{/* Permissions & Access Badges */}
					<TableCell className="w-[55%] py-4">
						<div className="flex flex-wrap gap-1.5 max-w-xl">
							<Skeleton className="h-5 w-24 rounded-md" />
							<Skeleton className="h-5 w-20 rounded-md" />
							<Skeleton className="h-5 w-28 rounded-md" />
							<Skeleton className="h-5 w-22 rounded-md" />
							<Skeleton className="h-5 w-14 rounded-md bg-blue-100/70" />
						</div>
					</TableCell>

					{/* Edit Action Button */}
					<TableCell className="w-[15%] text-right py-4">
						<div className="flex justify-end gap-2">
							<Skeleton className="h-8 w-16 rounded-lg" />
						</div>
					</TableCell>
				</TableRow>
			))}
		</>
	);
}
