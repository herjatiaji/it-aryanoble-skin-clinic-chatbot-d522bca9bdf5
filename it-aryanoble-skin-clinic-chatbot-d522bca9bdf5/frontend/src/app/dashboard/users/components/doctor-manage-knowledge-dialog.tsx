"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { RiCheckLine, RiLoader4Line, RiSearchLine } from "@remixicon/react";
import { useEffect, useState } from "react";
import { useCategories } from "../../category/hooks/use-categories";
import { UserResponse } from "../api/types";
import { useUpdateDoctorCategories } from "../hooks/use-users";

export function DoctorManageKnowledgeDialog({
	isOpen,
	onOpenChange,
	doctor,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	doctor: UserResponse | null;
}) {
	const { data: categories = [] } = useCategories();
	const updateCategories = useUpdateDoctorCategories();
	const [selectedIds, setSelectedIds] = useState<string[]>([]);
	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 200);

	useEffect(() => {
		if (isOpen && doctor) {
			setTimeout(() => {
				setSelectedIds(doctor.categories?.map((c) => c.id) || []);
				setSearchQuery("");
			}, 0);
		}
	}, [isOpen, doctor]);

	const handleToggle = (id: string) => {
		setSelectedIds((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]));
	};

	const handleSave = () => {
		if (doctor) {
			updateCategories.mutate(
				{ userId: doctor.id, categories: selectedIds },
				{
					onSuccess: () => {
						onOpenChange(false);
					},
				},
			);
		}
	};

	const filteredCategories = categories.filter((category) => {
		const query = debouncedSearch.toLowerCase().trim();
		if (!query) return true;
		return (
			category.name.toLowerCase().includes(query) ||
			(category.description && category.description.toLowerCase().includes(query))
		);
	});

	const handleToggleAll = () => {
		if (selectedIds.length > 0) {
			setSelectedIds([]);
		} else {
			setSelectedIds(categories.map((c) => c.id));
		}
	};

	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-md p-0 flex flex-col gap-0 rounded-lg overflow-hidden bg-white border border-gray-200 shadow-none">
				<DialogHeader className="p-4 border-b border-gray-100 flex flex-row items-center justify-between">
					<DialogTitle className="text-base font-semibold text-foreground">
						Manage Knowledge Base
					</DialogTitle>
					<DialogDescription className="sr-only">
						Manage doctor knowledge category assignments
					</DialogDescription>
				</DialogHeader>

				<div className="p-4 flex flex-col gap-3">
					{/* Search Bar */}
					<div className="relative">
						<RiSearchLine className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-400" />
						<Input
							type="text"
							placeholder="Search knowledge category..."
							value={searchQuery}
							onChange={(e) => setSearchQuery(e.target.value)}
							className="pl-9 border-gray-200 bg-white focus-visible:ring-blue-500 text-sm h-10 rounded-lg"
						/>
					</div>

					{/* Selection Controls */}
					{categories.length > 0 && (
						<div className="flex items-center justify-between px-1 text-xs text-zinc-500">
							<span>
								{selectedIds.length} of {categories.length} selected
							</span>
							<button
								type="button"
								onClick={handleToggleAll}
								className="font-medium text-blue-600 hover:text-blue-700 transition-colors cursor-pointer"
							>
								{selectedIds.length > 0 ? "Unselect All" : "Select All"}
							</button>
						</div>
					)}

					{/* List of knowledge */}
					<div className="flex flex-col gap-2.5 max-h-[50vh] overflow-y-auto pr-1">
						{filteredCategories.length === 0 ? (
							<div className="text-sm text-muted-foreground text-center py-6">
								{searchQuery.trim()
									? "No matching knowledge category found."
									: "No knowledge categories available."}
							</div>
						) : (
							filteredCategories.map((category) => {
								const isSelected = selectedIds.includes(category.id);
								return (
									<div
										key={category.id}
										className={`border rounded-lg p-3 flex items-center justify-between cursor-pointer transition-colors ${
											isSelected
												? "border-blue-500 bg-blue-50/60"
												: "border-gray-200 hover:bg-zinc-50"
										}`}
										onClick={() => handleToggle(category.id)}
									>
										<div className="flex items-center gap-3 w-full">
											<Checkbox
												id={`knowledge-${category.id}`}
												checked={isSelected}
												onCheckedChange={() => handleToggle(category.id)}
												className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
											/>
											<div className="flex flex-col">
												<span className="text-sm font-medium text-foreground">{category.name}</span>
												{category.description && (
													<span className="text-xs text-muted-foreground line-clamp-1">
														{category.description}
													</span>
												)}
											</div>
										</div>
									</div>
								);
							})
						)}
					</div>
				</div>

				<div className="p-4 border-t border-gray-100 flex items-center justify-end gap-2 bg-zinc-50/50">
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={updateCategories.isPending}
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
					>
						Cancel
					</Button>
					<Button
						className="bg-blue-600 text-white hover:bg-blue-700 px-4 h-10 rounded-lg font-medium text-sm transition-colors cursor-pointer shadow-none disabled:opacity-50"
						onClick={handleSave}
						disabled={updateCategories.isPending}
					>
						{updateCategories.isPending ? (
							<RiLoader4Line className="mr-1.5 h-4 w-4 animate-spin" />
						) : (
							<RiCheckLine className="mr-1.5 h-4 w-4" />
						)}
						{updateCategories.isPending ? "Saving..." : "Save Knowledge"}
					</Button>
				</div>
			</DialogContent>
		</Dialog>
	);
}
