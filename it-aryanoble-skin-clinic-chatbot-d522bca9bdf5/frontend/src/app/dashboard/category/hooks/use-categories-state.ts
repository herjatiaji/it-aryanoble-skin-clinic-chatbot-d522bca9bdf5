import { useSearchParams } from "next/navigation";
import { useDebounce } from "@/hooks/use-debounce";
import { usePagination } from "@/hooks/use-pagination";
import { useTableSort } from "@/hooks/use-table-sort";
import { useEffect, useMemo, useState } from "react";
import { CategoryResponse } from "../api/types";
import { useCategories, useDeleteCategory } from "./use-categories";

export function useCategoriesState() {
	const searchParams = useSearchParams();
	const initialSearch = searchParams.get("search") || "";
	const [searchQuery, setSearchQuery] = useState(initialSearch);

	useEffect(() => {
		const searchFromUrl = searchParams.get("search");
		if (searchFromUrl) {
			const timer = setTimeout(() => {
				setSearchQuery(searchFromUrl);
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [searchParams]);
	const debouncedSearch = useDebounce(searchQuery, 300);
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [dialogMode, setDialogMode] = useState<"add" | "edit">("add");
	const [selectedCategory, setSelectedCategory] = useState<CategoryResponse | null>(null);

	const [categoryToDelete, setCategoryToDelete] = useState<CategoryResponse | null>(null);
	const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

	const { data: categories = [], isLoading } = useCategories();
	const { mutate: deleteCategory, isPending: isDeleting } = useDeleteCategory();

	const { sortKey, sortOrder, handleSort, sortItems } = useTableSort({
		initialSortKey: "name",
		initialSortOrder: "asc",
	});

	const handleAddCategory = () => {
		setDialogMode("add");
		setSelectedCategory(null);
		setIsDialogOpen(true);
	};

	const handleEditCategory = (category: CategoryResponse) => {
		setDialogMode("edit");
		setSelectedCategory(category);
		setIsDialogOpen(true);
	};

	const handleDeleteClick = (category: CategoryResponse) => {
		setCategoryToDelete(category);
		setIsDeleteModalOpen(true);
	};

	const handleConfirmDelete = () => {
		if (!categoryToDelete) return;
		deleteCategory(categoryToDelete.id, {
			onSuccess: () => {
				setIsDeleteModalOpen(false);
				setCategoryToDelete(null);
			},
		});
	};

	const handleClearSearch = () => {
		setSearchQuery("");
	};

	// Filter categories based on search query
	const filteredCategories = useMemo(() => {
		let result = categories;
		if (debouncedSearch.trim()) {
			const q = debouncedSearch.toLowerCase();
			result = categories.filter((c) => c.name.toLowerCase().includes(q));
		}
		return sortItems<CategoryResponse>(result);
	}, [categories, debouncedSearch, sortItems]);

	const pagination = usePagination({ items: filteredCategories, initialPageSize: 10 });

	return {
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
		categories,
		filteredCategories,
		hasFilter: Boolean(debouncedSearch.trim()),
		pagination,
		handleAddCategory,
		handleEditCategory,
		handleDeleteClick,
		handleConfirmDelete,
		sortKey,
		sortOrder,
		handleSort,
	};
}
