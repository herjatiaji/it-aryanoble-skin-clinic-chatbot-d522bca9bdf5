import {
	Empty,
	EmptyDescription,
	EmptyHeader,
	EmptyMedia,
	EmptyTitle,
} from "@/components/ui/empty";
import { TableCell, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { RiInbox2Line } from "@remixicon/react";

interface TableEmptyStateProps {
	colSpan: number;
	title?: string;
	description?: string;
	onClearFilters?: () => void;
}

export function TableEmptyState({
	colSpan,
	title = "No data found",
	description = "There are no records matching your current criteria.",
	onClearFilters,
}: TableEmptyStateProps) {
	return (
		<TableRow>
			<TableCell colSpan={colSpan} className="py-12">
				<Empty className="border-0 bg-transparent py-2">
					<EmptyMedia
						variant="icon"
						className="bg-zinc-100 text-zinc-500 size-10 rounded-full"
					>
						<RiInbox2Line className="size-5" />
					</EmptyMedia>
					<EmptyHeader>
						<EmptyTitle className="text-sm font-semibold text-zinc-800">
							{title}
						</EmptyTitle>
						<EmptyDescription className="text-xs text-zinc-500">
							{description}
						</EmptyDescription>
					</EmptyHeader>
					{onClearFilters && (
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={onClearFilters}
							className="mt-3 text-xs border-gray-200 shadow-none cursor-pointer"
						>
							Clear filters
						</Button>
					)}
				</Empty>
			</TableCell>
		</TableRow>
	);
}
