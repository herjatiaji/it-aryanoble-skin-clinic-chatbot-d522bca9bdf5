"use client";

import { SortableTableHead, type SortOrder } from "@/components/shared/sortable-table-head";
import { TableEmptyState } from "@/components/shared/table-empty-state";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { BranchResponse } from "../api/types";
import { BranchesTableRow } from "./branches-table-row";
import { BranchesTableSkeleton } from "./skeletons/branches-table-skeleton";

interface BranchesTableProps {
	branches: BranchResponse[];
	isLoading: boolean;
	hasFilter: boolean;
	isGlobalLimitActive: boolean;
	globalBranchLimit: string;
	onClearFilter: () => void;
	sortKey?: string | null;
	sortOrder?: SortOrder;
	onSort?: (key: string) => void;
}

export function BranchesTable({
	branches,
	isLoading,
	hasFilter,
	isGlobalLimitActive,
	globalBranchLimit,
	onClearFilter,
	sortKey,
	sortOrder,
	onSort,
}: BranchesTableProps) {
	return (
		<div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
			<Table className="[&_tr]:border-gray-100">
				<TableHeader className="bg-gray-50/50">
					<TableRow className="hover:bg-gray-50/50 border-b-gray-100">
						<SortableTableHead
							sortKey="code"
							currentSortKey={sortKey}
							sortOrder={sortOrder}
							onSort={onSort}
							className="w-[15%]"
						>
							Branch Code
						</SortableTableHead>
						<TableHead className="w-[15%]">Ecosystem</TableHead>
						<SortableTableHead
							sortKey="name"
							currentSortKey={sortKey}
							sortOrder={sortOrder}
							onSort={onSort}
							className="w-[25%]"
						>
							Branch
						</SortableTableHead>
						<SortableTableHead
							sortKey="token_limit"
							currentSortKey={sortKey}
							sortOrder={sortOrder}
							onSort={onSort}
						>
							Tokens/Month
						</SortableTableHead>
						<TableHead>Used</TableHead>
						<SortableTableHead
							sortKey="remaining"
							currentSortKey={sortKey}
							sortOrder={sortOrder}
							onSort={onSort}
						>
							Remaining
						</SortableTableHead>
						<TableHead className="text-right">Actions</TableHead>
					</TableRow>
				</TableHeader>
				<TableBody>
					{isLoading ? (
						<BranchesTableSkeleton rows={5} />
					) : branches.length === 0 ? (
						<TableEmptyState
							colSpan={7}
							title="No branches found"
							description="There are no branches matching your search criteria."
							onClearFilters={hasFilter ? onClearFilter : undefined}
						/>
					) : (
						branches.map((branch) => (
							<BranchesTableRow
								key={branch.id}
								branch={branch}
								isGlobalLimitActive={isGlobalLimitActive}
								globalBranchLimit={globalBranchLimit}
							/>
						))
					)}
				</TableBody>
			</Table>
		</div>
	);
}
