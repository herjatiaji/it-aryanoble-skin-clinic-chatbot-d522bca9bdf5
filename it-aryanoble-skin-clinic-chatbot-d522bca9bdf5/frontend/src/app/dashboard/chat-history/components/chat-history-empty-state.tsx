import { Button } from "@/components/ui/button";
import {
	Empty,
	EmptyContent,
	EmptyDescription,
	EmptyHeader,
	EmptyMedia,
	EmptyTitle,
} from "@/components/ui/empty";
import { RiMessage3Line } from "@remixicon/react";

interface ChatHistoryEmptyStateProps {
	hasActiveFilters?: boolean;
	onResetFilters?: () => void;
}

export function ChatHistoryEmptyState({
	hasActiveFilters,
	onResetFilters,
}: ChatHistoryEmptyStateProps) {
	return (
		<div className="bg-white border border-gray-200 rounded-lg">
			<Empty className="py-12">
				<EmptyMedia variant="icon" className="bg-zinc-100 text-zinc-500 size-10 rounded-full">
					<RiMessage3Line className="size-5" />
				</EmptyMedia>
				<EmptyHeader>
					<EmptyTitle className="text-sm font-semibold text-zinc-800">
						{hasActiveFilters ? "No matching chat sessions" : "No chat history found."}
					</EmptyTitle>
					<EmptyDescription className="text-xs text-zinc-500 max-w-sm">
						{hasActiveFilters
							? "No conversation records matched your search query or filter criteria."
							: "There are no recorded chat sessions available yet."}
					</EmptyDescription>
				</EmptyHeader>
				{hasActiveFilters && onResetFilters && (
					<EmptyContent>
						<Button
							variant="outline"
							size="sm"
							onClick={onResetFilters}
							className="text-xs border-gray-200 cursor-pointer"
						>
							Clear filters
						</Button>
					</EmptyContent>
				)}
			</Empty>
		</div>
	);
}
