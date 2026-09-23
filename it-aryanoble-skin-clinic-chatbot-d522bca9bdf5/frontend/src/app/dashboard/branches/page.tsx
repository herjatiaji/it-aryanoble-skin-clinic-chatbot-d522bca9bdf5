"use client";

import { DataTablePagination } from "@/components/shared/data-table-pagination";
import { BranchesFilterBar } from "./components/branches-filter-bar";
import { BranchesTable } from "./components/branches-table";
import { useBranchesState } from "./hooks/use-branches-state";

export default function BranchPage() {
	const {
		searchQuery,
		setSearchQuery,
		handleClearSearch,
		isLoading,
		hasFilter,
		isGlobalLimitActive,
		globalBranchLimit,
		pagination,
		sortKey,
		sortOrder,
		handleSort,
	} = useBranchesState();

	return (
		<div className="flex flex-col flex-1 min-h-full bg-white p-6">
			<div className="flex flex-col gap-6 w-full">
				{/* Header */}
				<div className="flex flex-col gap-1">
					<h1 className="text-xl font-semibold text-foreground">Branch</h1>
					<p className="text-sm text-muted-foreground">Here is the overview data of the branches</p>
				</div>

				{/* Content */}
				<div className="flex flex-col gap-4">
					<BranchesFilterBar searchQuery={searchQuery} onSearchChange={setSearchQuery} />

					<BranchesTable
						branches={pagination.paginatedItems}
						isLoading={isLoading}
						hasFilter={hasFilter}
						isGlobalLimitActive={isGlobalLimitActive}
						globalBranchLimit={globalBranchLimit}
						onClearFilter={handleClearSearch}
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
						itemName="branches"
					/>
				</div>
			</div>
		</div>
	);
}
