import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { RiCheckLine } from "@remixicon/react";

import { useState } from "react";
import { CategoryResponse } from "../api/types";
import { useCreateCategory, useUpdateCategory } from "../hooks/use-categories";

interface CategoryDialogProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	mode: "add" | "edit";
	category?: CategoryResponse | null;
}

export function CategoryDialog({ isOpen, onOpenChange, mode, category }: CategoryDialogProps) {
	const isEdit = mode === "edit";
	const title = isEdit ? "Category" : "Add New Category";
	const buttonText = isEdit ? "Save Changes" : "Add Category";

	const [name, setName] = useState(isEdit && category ? category.name : "");

	const { mutate: createCategory, isPending: isCreating } = useCreateCategory();
	const { mutate: updateCategory, isPending: isUpdating } = useUpdateCategory();

	const isPending = isCreating || isUpdating;

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

	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-120 p-0 overflow-hidden bg-white rounded-xl">
				<form onSubmit={handleSubmit}>
					<DialogHeader className="p-4 border-b border-gray-100">
						<DialogTitle className="text-base font-medium text-gray-900">{title}</DialogTitle>
					</DialogHeader>

					<div className="p-4 flex flex-col gap-4">
						{isEdit && category && (
							<div className="flex flex-col gap-1.5">
								<label className="text-sm text-gray-900">Display</label>
								<div>
									<Badge variant="secondary" className="bg-black-50 text-black-500">
										{category.name}
									</Badge>
								</div>
							</div>
						)}

						<div className="flex flex-col gap-1.5">
							<label className="text-sm text-gray-900">Input Category Name</label>
							<div className="relative">
								<Input
									value={name}
									onChange={(e) => setName(e.target.value)}
									placeholder="Category Name"
									className="w-full bg-white h-10"
									disabled={isPending}
									autoFocus
								/>
							</div>
						</div>
					</div>

					<DialogFooter className="p-4 border-t border-gray-100 sm:justify-end">
						<Button
							type="submit"
							className="bg-black-50 hover:bg-black-50/80 text-black-500 font-medium px-5 disabled:opacity-50"
							disabled={isPending || !name.trim()}
						>
							<RiCheckLine className="size-4 mr-2" />
							{buttonText}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
