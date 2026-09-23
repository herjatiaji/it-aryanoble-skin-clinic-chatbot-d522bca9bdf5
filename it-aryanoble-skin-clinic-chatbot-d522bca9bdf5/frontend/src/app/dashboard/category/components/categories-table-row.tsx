import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { RiDeleteBinLine, RiEdit2Line } from "@remixicon/react";
import { CategoryResponse } from "../api/types";

interface CategoriesTableRowProps {
	category: CategoryResponse;
	isDeleting?: boolean;
	onEdit: (category: CategoryResponse) => void;
	onDelete: (category: CategoryResponse) => void;
}

export function CategoriesTableRow({
	category,
	isDeleting,
	onEdit,
	onDelete,
}: CategoriesTableRowProps) {
	return (
		<TableRow>
			<TableCell>
				<Badge variant="secondary" className="bg-black-50 text-black-500 hover:bg-black-50/80">
					{category.name}
				</Badge>
			</TableCell>
			<TableCell className="text-right">
				<div className="flex justify-end gap-2">
					<Button
						variant="outline"
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-3 h-8 font-medium text-xs transition-colors cursor-pointer shadow-none gap-1.5"
						onClick={() => onEdit(category)}
					>
						<RiEdit2Line className="size-3.5 shrink-0" />
						Edit
					</Button>
					<Button
						variant="outline"
						className="border-red-200 text-red-600 hover:bg-red-50 hover:border-red-300 rounded-lg px-3 h-8 font-medium text-xs transition-colors cursor-pointer shadow-none gap-1.5 disabled:opacity-50"
						onClick={() => onDelete(category)}
						disabled={isDeleting}
					>
						<RiDeleteBinLine className="size-3.5 shrink-0" />
						Delete
					</Button>
				</div>
			</TableCell>
		</TableRow>
	);
}
