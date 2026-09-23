import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";

interface CategoriesTableSkeletonProps {
	rows?: number;
}

export function CategoriesTableSkeleton({ rows = 5 }: CategoriesTableSkeletonProps) {
	return (
		<>
			{Array.from({ length: rows }).map((_, rIdx) => (
				<TableRow key={rIdx} className="hover:bg-transparent border-gray-100">
					{/* Category Badge Column */}
					<TableCell className="w-[35%] py-4">
						<Skeleton className="h-5 w-24 rounded-md" />
					</TableCell>

					{/* Actions Column */}
					<TableCell className="w-50 text-right py-4">
						<div className="flex justify-end gap-2">
							<Skeleton className="h-8 w-14 rounded-lg" />
							<Skeleton className="h-8 w-16 rounded-lg" />
						</div>
					</TableCell>
				</TableRow>
			))}
		</>
	);
}
