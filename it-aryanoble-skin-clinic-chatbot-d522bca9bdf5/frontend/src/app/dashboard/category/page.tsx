"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SearchBar } from "@/components/shared/search-bar";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { RiAddLine, RiDeleteBinLine, RiEdit2Line } from "@remixicon/react";
import { useState } from "react";
import { CategoryResponse } from "./api/types";
import { CategoryDialog } from "./components/category-dialog";
import { useCategories, useDeleteCategory } from "./hooks/use-categories";

export default function CategoriesPage() {
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [dialogMode, setDialogMode] = useState<"add" | "edit">("add");
	const [selectedCategory, setSelectedCategory] = useState<CategoryResponse | null>(null);

	const { data: categories, isLoading } = useCategories();
	const { mutate: deleteCategory, isPending: isDeleting } = useDeleteCategory();

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

	const handleDelete = (id: string) => {
		if (confirm("Are you sure you want to delete this category?")) {
			deleteCategory(id);
		}
	};

	return (
		<div className="p-6 flex flex-col gap-6 h-full">
			{/* Header */}
			<div className="flex flex-col gap-1">
				<h1 className="text-xl font-semibold text-gray-900">Category</h1>
				<p className="text-sm text-gray-500">Explore a wide array of categorized products.</p>
			</div>

			<div className="flex flex-col">
				{/* Actions */}
				<div className="flex items-center justify-between mb-4">
					<SearchBar
						containerClassName="max-w-md"
						placeholder="Search for category..."
					/>
					<Button className="bg-blue-500 hover:bg-blue-600" onClick={handleAddCategory}>
						<RiAddLine className="mr-2 h-4 w-4" />
						Add Category
					</Button>
				</div>

				{/* Table */}
				<div className="border border-gray-100 rounded-md bg-white overflow-hidden">
					<Table className="[&_tr]:border-gray-100">
						<TableHeader className="bg-gray-50/50">
							<TableRow>
								<TableHead className="w-[35%]">Category</TableHead>
								<TableHead className="w-50 text-right">Actions</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{isLoading ? (
								<TableRow>
									<TableCell colSpan={2} className="text-center py-8 text-gray-500">
										Loading categories...
									</TableCell>
								</TableRow>
							) : categories?.length === 0 ? (
								<TableRow>
									<TableCell colSpan={2} className="text-center py-8 text-gray-500">
										No categories found.
									</TableCell>
								</TableRow>
							) : (
								categories?.map((category) => (
									<TableRow key={category.id}>
										<TableCell>
											<Badge
												variant="secondary"
												className="bg-black-50 text-black-500 hover:bg-black-50/80"
											>
												{category.name}
											</Badge>
										</TableCell>
										<TableCell className="text-right">
											<div className="flex justify-end gap-2">
												<Button
													variant="outline"
													size="md"
													className="bg-white border-black-50 text-black-500 hover:bg-gray-50 font-medium"
													onClick={() => handleEditCategory(category)}
												>
													<RiEdit2Line className="size-4 mr-1.5" />
													Edit
												</Button>
												<Button
													variant="outline"
													size="md"
													className="bg-white border-black-50 text-black-500 hover:bg-gray-50 font-medium disabled:opacity-50"
													onClick={() => handleDelete(category.id)}
													disabled={isDeleting}
												>
													<RiDeleteBinLine className="size-4 mr-1.5" />
													Delete
												</Button>
											</div>
										</TableCell>
									</TableRow>
								))
							)}
						</TableBody>
					</Table>
				</div>
			</div>

			<CategoryDialog
				key={selectedCategory?.id || (isDialogOpen ? "open" : "closed")}
				isOpen={isDialogOpen}
				onOpenChange={setIsDialogOpen}
				mode={dialogMode}
				category={selectedCategory}
			/>
		</div>
	);
}
