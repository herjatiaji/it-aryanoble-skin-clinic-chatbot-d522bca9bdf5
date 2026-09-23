"use client";

import { SearchBar } from "@/components/shared/search-bar";
import { Button } from "@/components/ui/button";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { RiAddLine } from "@remixicon/react";
import type { BranchResponse } from "../api/types";
import { BranchFilterPopover } from "./branch-filter-popover";

interface UsersFilterBarProps {
	activeTab: string;
	searchQuery: string;
	onSearchChange: (query: string) => void;
	// Doctor filters
	doctorTypes: string[];
	selectedDrType: string;
	selectedDrTypeName: string;
	onSelectDrType: (val: string) => void;
	// Branch filters
	isBranchPopoverOpen: boolean;
	onBranchPopoverOpenChange: (open: boolean) => void;
	selectedBranches: string[];
	selectedBranchLabel: string;
	branchSearchQuery: string;
	onBranchSearchChange: (query: string) => void;
	filteredBranchOptions: BranchResponse[];
	isAllBranchesSelected: boolean;
	onToggleBranch: (id: string) => void;
	onToggleAllBranches: () => void;
	onResetBranches: () => void;
	// Add user action
	onAddNewUser: () => void;
}

export function UsersFilterBar({
	activeTab,
	searchQuery,
	onSearchChange,
	doctorTypes,
	selectedDrType,
	selectedDrTypeName,
	onSelectDrType,
	isBranchPopoverOpen,
	onBranchPopoverOpenChange,
	selectedBranches,
	selectedBranchLabel,
	branchSearchQuery,
	onBranchSearchChange,
	filteredBranchOptions,
	isAllBranchesSelected,
	onToggleBranch,
	onToggleAllBranches,
	onResetBranches,
	onAddNewUser,
}: UsersFilterBarProps) {
	return (
		<div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
			<div className="flex items-center gap-3 flex-1 flex-wrap">
				<SearchBar
					containerClassName="max-w-md w-full"
					placeholder={
						activeTab === "doctors"
							? "Search for doctor's name"
							: "Search for user, staff, or doctor..."
					}
					value={searchQuery}
					onChange={(e) => onSearchChange(e.target.value)}
				/>
				{activeTab === "doctors" && (
					<>
						<Select value={selectedDrType} onValueChange={(val) => onSelectDrType(val ?? "all")}>
							<SelectTrigger className="w-60 bg-white border-gray-200 text-gray-700 h-10 rounded-md">
								<SelectValue placeholder="Select doctor type">{selectedDrTypeName}</SelectValue>
							</SelectTrigger>
							<SelectContent alignItemWithTrigger={false} sideOffset={4} className="bg-white">
								<SelectItem value="all">Select doctor type</SelectItem>
								{doctorTypes.map((type) => (
									<SelectItem key={type} value={type}>
										{type}
									</SelectItem>
								))}
							</SelectContent>
						</Select>

						<BranchFilterPopover
							isOpen={isBranchPopoverOpen}
							onOpenChange={onBranchPopoverOpenChange}
							selectedBranches={selectedBranches}
							selectedBranchLabel={selectedBranchLabel}
							branchSearchQuery={branchSearchQuery}
							onBranchSearchChange={onBranchSearchChange}
							filteredBranchOptions={filteredBranchOptions}
							isAllBranchesSelected={isAllBranchesSelected}
							onToggleBranch={onToggleBranch}
							onToggleAllBranches={onToggleAllBranches}
							onResetBranches={onResetBranches}
						/>
					</>
				)}
			</div>
			{activeTab === "staff" && (
				<div className="flex items-center gap-2">
					<Button
						className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg h-10 px-4 font-medium text-sm transition-colors cursor-pointer shadow-none gap-2"
						onClick={onAddNewUser}
					>
						<RiAddLine className="size-4 shrink-0" />
						Add New User
					</Button>
				</div>
			)}
		</div>
	);
}
