"use client";

import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { DataTablePagination } from "@/components/shared/data-table-pagination";
import { CategoriesFilterBar } from "./components/categories-filter-bar";
import { CategoriesTable } from "./components/categories-table";
import { CategoryDialog } from "./components/category-dialog";
import { useCategoriesState } from "./hooks/use-categories-state";

export default function CategoriesPage() {
	const {
		searchQuery,
		setSearchQuery,
		handleClearSearch,
		isDialogOpen,
		setIsDialogOpen,
		dialogMode,
		selectedCategory,
		categoryToDelete,
		isDeleteModalOpen,
		setIsDeleteModalOpen,
		isLoading,
		isDeleting,
		hasFilter,
		pagination,
		handleAddCategory,
		handleEditCategory,
		handleDeleteClick,
		handleConfirmDelete,
		sortKey,
		sortOrder,
		handleSort,
	} = useCategoriesState();

	return (
		<div className="p-6 flex flex-col gap-6 h-full">
			{/* Header */}
			<div className="flex flex-col gap-1">
				<h1 className="text-xl font-semibold text-foreground">Category</h1>
				<p className="text-sm text-muted-foreground">
					Explore a wide array of categorized products.
				</p>
			</div>

			<div className="flex flex-col">
				<CategoriesFilterBar
					searchQuery={searchQuery}
					onSearchChange={setSearchQuery}
					onAddCategory={handleAddCategory}
				/>

				<CategoriesTable
					categories={pagination.paginatedItems}
					isLoading={isLoading}
					hasFilter={hasFilter}
					isDeleting={isDeleting}
					onClearFilter={handleClearSearch}
					onEditCategory={handleEditCategory}
					onDeleteCategory={handleDeleteClick}
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
					itemName="categories"
				/>
			</div>

			<CategoryDialog
				key={selectedCategory?.id || (isDialogOpen ? "open" : "closed")}
				isOpen={isDialogOpen}
				onOpenChange={setIsDialogOpen}
				mode={dialogMode}
				category={selectedCategory}
			/>

			{/* Delete Confirmation Modal */}
			<ConfirmationModal
				isOpen={isDeleteModalOpen}
				onOpenChange={setIsDeleteModalOpen}
				title="Delete Category"
				description={`Are you sure you want to delete the category "${categoryToDelete?.name || ""}"? This action cannot be undone.`}
				confirmText="Delete Category"
				variant="destructive"
				isLoading={isDeleting}
				onConfirm={handleConfirmDelete}
			/>
		</div>
	);
}
