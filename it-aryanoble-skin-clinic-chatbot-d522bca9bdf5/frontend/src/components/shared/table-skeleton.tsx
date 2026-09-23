import { Skeleton } from "@/components/ui/skeleton";
import { TableRow, TableCell } from "@/components/ui/table";

interface TableSkeletonProps {
	columns: number;
	rows?: number;
	cellHeight?: string;
}

export function TableSkeleton({
	columns,
	rows = 5,
	cellHeight = "h-4",
}: TableSkeletonProps) {
	return (
		<>
			{Array.from({ length: rows }).map((_, rIdx) => (
				<TableRow key={rIdx} className="hover:bg-transparent">
					{Array.from({ length: columns }).map((_, cIdx) => (
						<TableCell key={cIdx} className="py-4">
							<Skeleton className={`w-full max-w-[85%] rounded ${cellHeight}`} />
						</TableCell>
					))}
				</TableRow>
			))}
		</>
	);
}
