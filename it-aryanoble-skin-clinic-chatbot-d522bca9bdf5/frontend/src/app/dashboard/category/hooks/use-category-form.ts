import { useEffect, useState } from "react";
import { CategoryResponse } from "../api/types";
import { useCreateCategory, useUpdateCategory } from "./use-categories";

interface UseCategoryFormProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	mode: "add" | "edit";
	category?: CategoryResponse | null;
}

export function useCategoryForm({
	isOpen,
	onOpenChange,
	mode,
	category,
}: UseCategoryFormProps) {
	const isEdit = mode === "edit";
	const title = isEdit ? "Category" : "Add New Category";
	const buttonText = isEdit ? "Save Changes" : "Add Category";

	const [name, setName] = useState(isEdit && category ? category.name : "");

	const { mutate: createCategory, isPending: isCreating } = useCreateCategory();
	const { mutate: updateCategory, isPending: isUpdating } = useUpdateCategory();

	const isPending = isCreating || isUpdating;

	useEffect(() => {
		if (isOpen) {
			const timer = setTimeout(() => {
				setName(isEdit && category ? category.name : "");
			}, 0);
			return () => clearTimeout(timer);
		} else {
			const timer = setTimeout(() => {
				setName("");
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [isOpen, isEdit, category]);

	const handleSubmit = (e: React.FormEvent) => {
		e.preventDefault();
		if (!name.trim()) return;

		if (isEdit && category) {
			updateCategory(
				{ id: category.id, data: { name } },
				{
					onSuccess: () => onOpenChange(false),
				},
			);
		} else {
			createCategory(
				{ name },
				{
					onSuccess: () => onOpenChange(false),
				},
			);
		}
	};

	return {
		name,
		setName,
		title,
		buttonText,
		isEdit,
		isPending,
		handleSubmit,
	};
}
