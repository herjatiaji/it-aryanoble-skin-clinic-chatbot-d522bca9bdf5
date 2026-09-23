"use client";

import { DataTablePagination } from "@/components/shared/data-table-pagination";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DoctorDetailsSheet } from "./components/doctor-details-sheet";
import { DoctorTable } from "./components/doctor-table";
import { StaffTable } from "./components/staff-table";
import { UserAddSheet } from "./components/user-add-sheet";
import { UserStaffProfileSheet } from "./components/user-staff-profile-sheet";
import { UsersFilterBar } from "./components/users-filter-bar";
import { useUsersState } from "./hooks/use-users-state";

export default function UsersPage() {
	const {
		activeTab,
		setActiveTab,
		searchQuery,
		setSearchQuery,
		selectedDrType,
		setSelectedDrType,
		doctorTypes,
		selectedDrTypeName,
		selectedBranches,
		selectedBranchLabel,
		isBranchPopoverOpen,
		setIsBranchPopoverOpen,
		branchSearchQuery,
		setBranchSearchQuery,
		filteredBranchOptions,
		isAllBranchesSelected,
		handleToggleBranch,
		handleToggleAllBranches,
		handleResetBranches,
		// Data & Loading
		isStaffLoading,
		isDoctorLoading,
		// Pagination
		staffPagination,
		doctorPagination,
		// Modals & Selection
		selectedDoctorLive,
		isSheetOpen,
		setIsSheetOpen,
		handleViewDoctor,
		selectedStaffLive,
		isViewStaffOpen,
		setIsViewStaffOpen,
		handleViewStaff,
		isAddUserOpen,
		setIsAddUserOpen,
		// Filters
		hasStaffFilter,
		hasDoctorFilter,
		handleClearStaffFilter,
		handleClearDoctorFilter,
		// Sorting
		staffSortKey,
		staffSortOrder,
		handleStaffSort,
		doctorSortKey,
		doctorSortOrder,
		handleDoctorSort,
	} = useUsersState();

	return (
		<div className="flex flex-col h-full gap-6 p-6">
			{/* Header */}
			<div className="flex flex-col gap-1">
				<h1 className="text-xl font-semibold text-foreground">User Management</h1>
				<p className="text-sm text-muted-foreground">
					Easily handle staff accounts and doctor credentials.
				</p>
			</div>

			<Tabs defaultValue="staff" value={activeTab} onValueChange={setActiveTab} className="w-full">
				<TabsList variant="line" className="mb-6">
					<TabsTrigger
						value="staff"
						className="font-medium text-sm text-zinc-600 hover:text-blue-700 data-active:text-blue-700 data-active:after:bg-blue-700"
					>
						Staff
					</TabsTrigger>
					<TabsTrigger
						value="doctors"
						className="font-medium text-sm text-zinc-600 hover:text-blue-700 data-active:text-blue-700 data-active:after:bg-blue-700"
					>
						Doctor
					</TabsTrigger>
				</TabsList>

				<UsersFilterBar
					activeTab={activeTab}
					searchQuery={searchQuery}
					onSearchChange={setSearchQuery}
					doctorTypes={doctorTypes}
					selectedDrType={selectedDrType}
					selectedDrTypeName={selectedDrTypeName}
					onSelectDrType={setSelectedDrType}
					isBranchPopoverOpen={isBranchPopoverOpen}
					onBranchPopoverOpenChange={setIsBranchPopoverOpen}
					selectedBranches={selectedBranches}
					selectedBranchLabel={selectedBranchLabel}
					branchSearchQuery={branchSearchQuery}
					onBranchSearchChange={setBranchSearchQuery}
					filteredBranchOptions={filteredBranchOptions}
					isAllBranchesSelected={isAllBranchesSelected}
					onToggleBranch={handleToggleBranch}
					onToggleAllBranches={handleToggleAllBranches}
					onResetBranches={handleResetBranches}
					onAddNewUser={() => setIsAddUserOpen(true)}
				/>

				{/* Staff Tab Content */}
				<TabsContent value="staff" className="mt-0 outline-none">
					<StaffTable
						staff={staffPagination.paginatedItems}
						isLoading={isStaffLoading}
						hasFilter={hasStaffFilter}
						onClearFilter={handleClearStaffFilter}
						onViewStaff={handleViewStaff}
						sortKey={staffSortKey}
						sortOrder={staffSortOrder}
						onSort={handleStaffSort}
					/>

					<DataTablePagination
						page={staffPagination.page}
						pageSize={staffPagination.pageSize}
						totalPages={staffPagination.totalPages}
						totalItems={staffPagination.totalItems}
						startIndex={staffPagination.startIndex}
						endIndex={staffPagination.endIndex}
						onPageChange={staffPagination.setPage}
						onPageSizeChange={staffPagination.setPageSize}
						itemName="staff members"
					/>
				</TabsContent>

				{/* Doctors Tab Content */}
				<TabsContent value="doctors" className="mt-0 outline-none">
					<DoctorTable
						doctors={doctorPagination.paginatedItems}
						isLoading={isDoctorLoading}
						hasFilter={hasDoctorFilter}
						onClearFilter={handleClearDoctorFilter}
						onViewDoctor={handleViewDoctor}
						sortKey={doctorSortKey}
						sortOrder={doctorSortOrder}
						onSort={handleDoctorSort}
					/>

					<DataTablePagination
						page={doctorPagination.page}
						pageSize={doctorPagination.pageSize}
						totalPages={doctorPagination.totalPages}
						totalItems={doctorPagination.totalItems}
						startIndex={doctorPagination.startIndex}
						endIndex={doctorPagination.endIndex}
						onPageChange={doctorPagination.setPage}
						onPageSizeChange={doctorPagination.setPageSize}
						itemName="doctors"
					/>
				</TabsContent>
			</Tabs>

			<DoctorDetailsSheet
				isOpen={isSheetOpen}
				onOpenChange={setIsSheetOpen}
				doctor={selectedDoctorLive}
			/>

			<UserAddSheet isOpen={isAddUserOpen} onOpenChange={setIsAddUserOpen} />

			<UserStaffProfileSheet
				isOpen={isViewStaffOpen}
				onOpenChange={setIsViewStaffOpen}
				staff={selectedStaffLive}
			/>
		</div>
	);
}
