import { SearchBar } from "@/components/shared/search-bar";
import { Button } from "@/components/ui/button";
import { RiAddLine } from "@remixicon/react";

interface CategoriesFilterBarProps {
	searchQuery: string;
	onSearchChange: (value: string) => void;
	onAddCategory: () => void;
}

export function CategoriesFilterBar({
	searchQuery,
	onSearchChange,
	onAddCategory,
}: CategoriesFilterBarProps) {
	return (
		<div className="flex items-center justify-between mb-4">
			<SearchBar
				containerClassName="max-w-md"
				placeholder="Search for category..."
				value={searchQuery}
				onChange={(e) => onSearchChange(e.target.value)}
			/>
			<Button
				className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg h-10 px-4 font-medium text-sm transition-colors cursor-pointer shadow-none gap-2"
				onClick={onAddCategory}
			>
				<RiAddLine className="size-4 shrink-0" />
				Add Category
			</Button>
		</div>
	);
}
