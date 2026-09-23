"use client";

import { SortableTableHead, type SortOrder } from "@/components/shared/sortable-table-head";
import { TableEmptyState } from "@/components/shared/table-empty-state";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RoleDetailResponse } from "../api/types";
import { RolesTableRow } from "./roles-table-row";
import { RolesTableSkeleton } from "./skeletons/roles-table-skeleton";

interface RolesTableProps {
	roles: RoleDetailResponse[];
	isLoading: boolean;
	hasFilter: boolean;
	onClearFilter?: () => void;
	onEditRole: (role: RoleDetailResponse) => void;
	sortKey?: string | null;
	sortOrder?: SortOrder;
	onSort?: (key: string) => void;
}

export function RolesTable({
	roles,
	isLoading,
	hasFilter,
	onClearFilter,
	onEditRole,
	sortKey,
	sortOrder,
	onSort,
}: RolesTableProps) {
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
							className="w-[30%]"
						>
							Role Name
						</SortableTableHead>
						<TableHead className="w-[55%]">Permissions & Access</TableHead>
						<TableHead className="w-[15%] text-right">Actions</TableHead>
					</TableRow>
				</TableHeader>
				<TableBody>
					{isLoading ? (
						<RolesTableSkeleton rows={5} />
					) : roles.length === 0 ? (
						<TableEmptyState
							colSpan={3}
							title="No roles found"
							description={
								hasFilter
									? "No roles match your search criteria. Try a different search query."
									: 'No roles have been created yet. Click "Add New Role" to create one.'
							}
							onClearFilters={hasFilter ? onClearFilter : undefined}
						/>
					) : (
						roles.map((role) => <RolesTableRow key={role.id} role={role} onEdit={onEditRole} />)
					)}
				</TableBody>
			</Table>
		</div>
	);
}
