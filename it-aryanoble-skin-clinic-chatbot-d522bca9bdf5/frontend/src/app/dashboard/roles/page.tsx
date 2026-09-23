"use client";

import { DataTablePagination } from "@/components/shared/data-table-pagination";
import { RoleDialog } from "./components/role-dialog";
import { RolesFilterBar } from "./components/roles-filter-bar";
import { RolesTable } from "./components/roles-table";
import { useRolesState } from "./hooks/use-roles-state";

export default function RolesPage() {
	const {
		searchQuery,
		setSearchQuery,
		handleClearSearch,
		selectedRoleLive,
		roleDialogMode,
		isRoleDialogOpen,
		setIsRoleDialogOpen,
		handleAddRole,
		handleEditRole,
		isLoading,
		pagination,
		sortKey,
		sortOrder,
		handleSort,
	} = useRolesState();

	return (
		<div className="flex flex-col h-full gap-6 p-6">
			{/* Header */}
			<div className="flex flex-col gap-1">
				<h1 className="text-xl font-semibold text-foreground">Roles & Permissions</h1>
				<p className="text-sm text-muted-foreground">
					Configure user roles and granular access permissions across modules.
				</p>
			</div>

			<div className="flex flex-col">
				<RolesFilterBar
					searchQuery={searchQuery}
					onSearchChange={setSearchQuery}
					onAddRole={handleAddRole}
				/>

				<RolesTable
					roles={pagination.paginatedItems}
					isLoading={isLoading}
					hasFilter={Boolean(searchQuery.trim())}
					onClearFilter={handleClearSearch}
					onEditRole={handleEditRole}
					sortKey={sortKey}
					sortOrder={sortOrder}
					onSort={handleSort}
				/>

				<DataTablePagination
					page={pagination.page}
					pageSize={pagination.pageSize}
					totalPages={pagination.totalPages}
					totalItems={pagination.totalItems}
					startIndex={pagination.startIndex}
					endIndex={pagination.endIndex}
					onPageChange={pagination.setPage}
					onPageSizeChange={pagination.setPageSize}
					itemName="roles"
				/>
			</div>

			<RoleDialog
				isOpen={isRoleDialogOpen}
				onOpenChange={setIsRoleDialogOpen}
				role={selectedRoleLive}
				mode={roleDialogMode}
			/>
		</div>
	);
}
