"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldContent, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RiCheckLine, RiLoader4Line } from "@remixicon/react";
import { CategoryResponse } from "../api/types";
import { useCategoryForm } from "../hooks/use-category-form";

interface CategoryDialogProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	mode: "add" | "edit";
	category?: CategoryResponse | null;
}

export function CategoryDialog({ isOpen, onOpenChange, mode, category }: CategoryDialogProps) {
	const { name, setName, title, buttonText, isEdit, isPending, handleSubmit } = useCategoryForm({
		isOpen,
		onOpenChange,
		mode,
		category,
	});

	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent className="max-w-120 p-0 overflow-hidden bg-white rounded-lg border border-gray-200 shadow-none">
				<form onSubmit={handleSubmit}>
					<DialogHeader className="p-4 border-b border-gray-100">
						<DialogTitle className="text-base font-semibold text-foreground">{title}</DialogTitle>
						<DialogDescription className="sr-only">
							{isEdit ? "Edit existing category name" : "Add new knowledge category"}
						</DialogDescription>
					</DialogHeader>

					<div className="p-4 flex flex-col gap-4">
						{isEdit && category && (
							<Field>
								<FieldLabel>
									<FieldTitle className="text-xs font-medium text-zinc-700">Display</FieldTitle>
								</FieldLabel>
								<FieldContent>
									<div>
										<Badge variant="secondary" className="bg-gray-100 text-gray-700 rounded-md">
											{category.name}
										</Badge>
									</div>
								</FieldContent>
							</Field>
						)}

						<Field>
							<FieldLabel>
								<FieldTitle className="text-xs font-medium text-zinc-700">Category Name</FieldTitle>
							</FieldLabel>
							<FieldContent>
								<div className="relative">
									<Input
										value={name}
										onChange={(e) => setName(e.target.value)}
										placeholder="Category Name"
										className="border-gray-200 bg-white focus-visible:ring-blue-500 w-full h-10 rounded-lg text-sm"
										disabled={isPending}
										autoFocus
									/>
								</div>
							</FieldContent>
						</Field>
					</div>

					<DialogFooter className="p-4 border-t border-gray-100 flex items-center justify-end gap-2 bg-zinc-50/50">
						<Button
							type="button"
							variant="outline"
							onClick={() => onOpenChange(false)}
							disabled={isPending}
							className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						>
							Cancel
						</Button>
						<Button
							type="submit"
							className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none disabled:opacity-50"
							disabled={isPending || !name.trim()}
						>
							{isPending ? (
								<RiLoader4Line className="size-4 mr-1.5 animate-spin" />
							) : (
								<RiCheckLine className="size-4 mr-1.5" />
							)}
							{isPending ? (isEdit ? "Saving..." : "Adding...") : buttonText}
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}
