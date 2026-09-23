import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";

interface DoctorTableSkeletonProps {
	rows?: number;
}

export function DoctorTableSkeleton({ rows = 5 }: DoctorTableSkeletonProps) {
	return (
		<>
			{Array.from({ length: rows }).map((_, rIdx) => (
				<TableRow key={rIdx} className="hover:bg-transparent border-gray-100">
					{/* Name & Avatar Column */}
					<TableCell className="w-[20%] py-3">
						<div className="flex items-center gap-3">
							<Skeleton className="h-10 w-10 rounded-full shrink-0" />
							<Skeleton className="h-4 w-28 rounded" />
						</div>
					</TableCell>

					{/* Employee ID Column */}
					<TableCell className="w-[15%] py-3">
						<Skeleton className="h-4 w-20 rounded" />
					</TableCell>

					{/* Dr Type Column */}
					<TableCell className="w-[15%] py-3">
						<Skeleton className="h-4 w-16 rounded" />
					</TableCell>

					{/* Branch Column */}
					<TableCell className="w-[15%] py-3">
						<Skeleton className="h-4 w-24 rounded" />
					</TableCell>

					{/* Ecosystem Column */}
					<TableCell className="w-[10%] py-3">
						<Skeleton className="h-4 w-14 rounded" />
					</TableCell>

					{/* Email Column */}
					<TableCell className="w-[20%] py-3">
						<Skeleton className="h-4 w-36 rounded" />
					</TableCell>

					{/* Action Button Column */}
					<TableCell className="w-10 text-right py-3">
						<div className="flex justify-end">
							<Skeleton className="h-8 w-16 rounded-lg" />
						</div>
					</TableCell>
				</TableRow>
			))}
		</>
	);
}
