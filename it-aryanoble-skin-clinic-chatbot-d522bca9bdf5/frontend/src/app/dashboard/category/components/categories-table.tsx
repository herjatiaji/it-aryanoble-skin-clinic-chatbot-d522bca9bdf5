"use client";

import { SortableTableHead, type SortOrder } from "@/components/shared/sortable-table-head";
import { TableEmptyState } from "@/components/shared/table-empty-state";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CategoryResponse } from "../api/types";
import { CategoriesTableRow } from "./categories-table-row";
import { CategoriesTableSkeleton } from "./skeletons/categories-table-skeleton";

interface CategoriesTableProps {
	categories: CategoryResponse[];
	isLoading: boolean;
	hasFilter: boolean;
	isDeleting?: boolean;
	onClearFilter?: () => void;
	onEditCategory: (category: CategoryResponse) => void;
	onDeleteCategory: (category: CategoryResponse) => void;
	sortKey?: string | null;
	sortOrder?: SortOrder;
	onSort?: (key: string) => void;
}

export function CategoriesTable({
	categories,
	isLoading,
	hasFilter,
	isDeleting,
	onClearFilter,
	onEditCategory,
	onDeleteCategory,
	sortKey,
	sortOrder,
	onSort,
}: CategoriesTableProps) {
	return (
		<div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
			<Table className="[&_tr]:border-gray-100">
				<TableHeader className="bg-gray-50/50">
					<TableRow>
						<SortableTableHead
							sortKey="name"
							currentSortKey={sortKey}
							sortOrder={sortOrder}
							onSort={onSort}
							className="w-[35%]"
						>
							Category
						</SortableTableHead>
						<TableHead className="w-50 text-right">Actions</TableHead>
					</TableRow>
				</TableHeader>
				<TableBody>
					{isLoading ? (
						<CategoriesTableSkeleton rows={5} />
					) : categories.length === 0 ? (
						<TableEmptyState
							colSpan={2}
							title="No categories found"
							description={
								hasFilter
									? "No categories match your search criteria. Try a different search query."
									: "There are no categories available."
							}
							onClearFilters={hasFilter ? onClearFilter : undefined}
						/>
					) : (
						categories.map((category) => (
							<CategoriesTableRow
								key={category.id}
								category={category}
								isDeleting={isDeleting}
								onEdit={onEditCategory}
								onDelete={onDeleteCategory}
							/>
						))
					)}
				</TableBody>
			</Table>
		</div>
	);
}
