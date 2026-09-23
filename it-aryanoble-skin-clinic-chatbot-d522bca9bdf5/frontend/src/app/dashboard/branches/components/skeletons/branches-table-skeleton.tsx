import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";

interface BranchesTableSkeletonProps {
	rows?: number;
}

export function BranchesTableSkeleton({ rows = 5 }: BranchesTableSkeletonProps) {
	return (
		<>
			{Array.from({ length: rows }).map((_, rIdx) => (
				<TableRow key={rIdx} className="hover:bg-transparent border-gray-100">
					{/* Branch Code Column */}
					<TableCell className="w-[15%] py-4">
						<Skeleton className="h-4 w-20 rounded" />
					</TableCell>

					{/* Ecosystem Column */}
					<TableCell className="w-[15%] py-4">
						<Skeleton className="h-4 w-24 rounded" />
					</TableCell>

					{/* Branch Name Column */}
					<TableCell className="w-[25%] py-4">
						<Skeleton className="h-4 w-36 rounded" />
					</TableCell>

					{/* Tokens/Month Column */}
					<TableCell className="py-4">
						<Skeleton className="h-4 w-20 rounded" />
					</TableCell>

					{/* Used Column */}
					<TableCell className="py-4">
						<Skeleton className="h-4 w-16 rounded" />
					</TableCell>

					{/* Remaining Column */}
					<TableCell className="py-4">
						<Skeleton className="h-4 w-16 rounded" />
					</TableCell>

					{/* Actions Column */}
					<TableCell className="text-right py-4">
						<div className="flex justify-end">
							<Skeleton className="h-8 w-16 rounded-lg" />
						</div>
					</TableCell>
				</TableRow>
			))}
		</>
	);
}
