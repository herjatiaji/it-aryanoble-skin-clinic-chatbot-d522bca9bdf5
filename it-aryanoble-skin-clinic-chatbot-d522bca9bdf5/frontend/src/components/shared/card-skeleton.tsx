import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

interface CardSkeletonProps {
	count?: number;
	className?: string;
}

export function CardSkeleton({
	count = 3,
	className = "grid grid-cols-1 md:grid-cols-3 gap-4",
}: CardSkeletonProps) {
	return (
		<div className={className}>
			{Array.from({ length: count }).map((_, idx) => (
				<Card key={idx} className="border-gray-200 bg-white shadow-none">
					<CardHeader className="pb-2 space-y-2">
						<Skeleton className="h-4 w-28" />
						<Skeleton className="h-7 w-16" />
					</CardHeader>
					<CardContent>
						<Skeleton className="h-3.5 w-full" />
					</CardContent>
				</Card>
			))}
		</div>
	);
}
