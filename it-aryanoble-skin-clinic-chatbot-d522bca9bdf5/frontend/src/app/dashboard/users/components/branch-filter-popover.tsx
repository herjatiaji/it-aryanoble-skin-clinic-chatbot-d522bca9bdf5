"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RiArrowDownSLine, RiCloseLine, RiSearchLine } from "@remixicon/react";
import type { BranchResponse } from "../api/types";

interface BranchFilterPopoverProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	selectedBranches: string[];
	selectedBranchLabel: string;
	branchSearchQuery: string;
	onBranchSearchChange: (query: string) => void;
	filteredBranchOptions: BranchResponse[];
	isAllBranchesSelected: boolean;
	onToggleBranch: (id: string) => void;
	onToggleAllBranches: () => void;
	onResetBranches: () => void;
}

export function BranchFilterPopover({
	isOpen,
	onOpenChange,
	selectedBranches,
	selectedBranchLabel,
	branchSearchQuery,
	onBranchSearchChange,
	filteredBranchOptions,
	isAllBranchesSelected,
	onToggleBranch,
	onToggleAllBranches,
	onResetBranches,
}: BranchFilterPopoverProps) {
	return (
		<Popover open={isOpen} onOpenChange={onOpenChange}>
			<PopoverTrigger
				render={
					<Button
						type="button"
						variant="outline"
						className="min-w-64 w-auto justify-between font-normal text-sm bg-white border-gray-200 focus-visible:ring-blue-500 shadow-none h-10 rounded-md text-gray-700 hover:bg-zinc-50 cursor-pointer gap-2"
					>
						<span className="truncate">{selectedBranchLabel}</span>
						<RiArrowDownSLine className="size-4 text-zinc-400 shrink-0 ml-auto" />
					</Button>
				}
			/>
			<PopoverContent
				align="start"
				className="min-w-(--anchor-width) w-max max-w-sm p-2.5 flex flex-col gap-2 z-60 bg-white border border-gray-200 shadow-none rounded-lg"
			>
				{/* Search Bar inside Combobox */}
				<div className="relative w-full">
					<RiSearchLine className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-zinc-400 pointer-events-none" />
					<Input
						placeholder="Search branch..."
						value={branchSearchQuery}
						onChange={(e) => onBranchSearchChange(e.target.value)}
						className="h-8 pl-8 pr-7 text-xs bg-zinc-50 border-gray-200 focus-visible:ring-blue-500 rounded-md"
						autoFocus
					/>
					{branchSearchQuery && (
						<button
							type="button"
							onClick={() => onBranchSearchChange("")}
							className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 cursor-pointer"
						>
							<RiCloseLine className="size-3.5" />
						</button>
					)}
				</div>

				{/* Branch Options List */}
				<div className="flex flex-col gap-0.5 max-h-56 overflow-y-auto overscroll-contain pr-1">
					{!branchSearchQuery && (
						<>
							<div
								className="flex items-center gap-2 p-1.5 hover:bg-zinc-50 rounded-md cursor-pointer transition-colors"
								onClick={onToggleAllBranches}
							>
								<Checkbox
									checked={isAllBranchesSelected}
									onCheckedChange={onToggleAllBranches}
									className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
								/>
								<span className="text-xs font-medium text-zinc-900">All Branches</span>
							</div>
							<div className="h-px bg-zinc-100 my-1" />
						</>
					)}

					{filteredBranchOptions.length === 0 ? (
						<div className="py-4 text-center text-xs text-zinc-500">No branches found</div>
					) : (
						filteredBranchOptions.map((b) => {
							const isChecked = isAllBranchesSelected || selectedBranches.includes(b.id);
							return (
								<div
									key={b.id}
									className="flex items-center gap-2 p-1.5 hover:bg-zinc-50 rounded-md cursor-pointer transition-colors"
									onClick={() => onToggleBranch(b.id)}
								>
									<Checkbox
										checked={isChecked}
										onCheckedChange={() => onToggleBranch(b.id)}
										className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
									/>
									<span className="text-xs font-normal text-zinc-800 flex-1 whitespace-normal leading-snug">
										{b.name}
									</span>
								</div>
							);
						})
					)}
				</div>

				{/* Footer */}
				<div className="pt-1.5 border-t border-zinc-100 flex items-center justify-between text-[11px] text-zinc-500">
					<span>
						{isAllBranchesSelected || selectedBranches.length === 0
							? "All branches selected"
							: `${selectedBranches.length} selected`}
					</span>
					{selectedBranches.length > 0 && (
						<button
							type="button"
							onClick={onResetBranches}
							className="text-blue-600 hover:underline cursor-pointer font-medium"
						>
							Reset
						</button>
					)}
				</div>
			</PopoverContent>
		</Popover>
	);
}
