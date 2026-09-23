import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";

interface StaffTableSkeletonProps {
	rows?: number;
}

export function StaffTableSkeleton({ rows = 5 }: StaffTableSkeletonProps) {
	return (
		<>
			{Array.from({ length: rows }).map((_, rIdx) => (
				<TableRow key={rIdx} className="hover:bg-transparent border-gray-100">
					{/* Name & Avatar Column */}
					<TableCell className="w-[35%] py-3">
						<div className="flex items-center gap-3">
							<Skeleton className="h-10 w-10 rounded-full shrink-0" />
							<Skeleton className="h-4 w-32 rounded" />
						</div>
					</TableCell>

					{/* Role Column */}
					<TableCell className="w-[20%] py-3">
						<Skeleton className="h-5 w-16 rounded-md" />
					</TableCell>

					{/* Email Column */}
					<TableCell className="py-3">
						<Skeleton className="h-4 w-44 rounded" />
					</TableCell>

					{/* Action Button Column */}
					<TableCell className="w-30 text-right py-3">
						<div className="flex justify-end">
							<Skeleton className="h-8 w-16 rounded-lg" />
						</div>
					</TableCell>
				</TableRow>
			))}
		</>
	);
}
