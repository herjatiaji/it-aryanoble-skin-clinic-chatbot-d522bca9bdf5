"use client";

import { SortableTableHead, type SortOrder } from "@/components/shared/sortable-table-head";
import { TableEmptyState } from "@/components/shared/table-empty-state";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { UserResponse } from "../api/types";
import { StaffTableSkeleton } from "./skeletons/staff-table-skeleton";
import { StaffTableRow } from "./staff-table-row";

interface StaffTableProps {
	staff: UserResponse[];
	isLoading: boolean;
	hasFilter: boolean;
	onClearFilter?: () => void;
	onViewStaff: (staff: UserResponse) => void;
	sortKey?: string | null;
	sortOrder?: SortOrder;
	onSort?: (key: string) => void;
}

export function StaffTable({
	staff,
	isLoading,
	hasFilter,
	onClearFilter,
	onViewStaff,
	sortKey,
	sortOrder,
	onSort,
}: StaffTableProps) {
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
							Name
						</SortableTableHead>
						<TableHead className="w-[20%]">Role</TableHead>
						<SortableTableHead
							sortKey="email"
							currentSortKey={sortKey}
							sortOrder={sortOrder}
							onSort={onSort}
						>
							Email
						</SortableTableHead>
						<TableHead className="w-30 text-right">Actions</TableHead>
					</TableRow>
				</TableHeader>
				<TableBody>
					{isLoading ? (
						<StaffTableSkeleton rows={5} />
					) : staff.length === 0 ? (
						<TableEmptyState
							colSpan={4}
							title="No staff members found."
							description="There are no staff members matching your search criteria."
							onClearFilters={hasFilter ? onClearFilter : undefined}
						/>
					) : (
						staff.map((member) => (
							<StaffTableRow key={member.id} staff={member} onView={onViewStaff} />
						))
					)}
				</TableBody>
			</Table>
		</div>
	);
}
