"use client";

import { SearchBar } from "@/components/shared/search-bar";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuRadioGroup,
	DropdownMenuRadioItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
	RiArrowDownSLine,
	RiCheckLine,
	RiCloseLine,
	RiFilterOffLine,
	RiMedicineBottleLine,
	RiSearchLine,
	RiUserLine,
} from "@remixicon/react";
import { useMemo, useState } from "react";
import { NotificationFilterTab } from "../hooks/use-notifications-state";

interface NotificationFilterBarProps {
	activeTab: NotificationFilterTab;
	onTabChange: (tab: NotificationFilterTab) => void;
	searchQuery: string;
	onSearchChange: (query: string) => void;
	totalCount: number;
	unreadCount: number;
	readCount: number;
	hasActiveFilters: boolean;
	onResetFilters: () => void;
	doctorFilter: string;
	onDoctorFilterChange: (doctor: string) => void;
	doctors: string[];
	doctorTypeFilter: string;
	onDoctorTypeFilterChange: (type: string) => void;
	doctorTypes: string[];
}

export function NotificationFilterBar({
	activeTab,
	onTabChange,
	searchQuery,
	onSearchChange,
	totalCount,
	unreadCount,
	readCount,
	hasActiveFilters,
	onResetFilters,
	doctorFilter,
	onDoctorFilterChange,
	doctors,
	doctorTypeFilter,
	onDoctorTypeFilterChange,
	doctorTypes,
}: NotificationFilterBarProps) {
	const [isDoctorPopoverOpen, setIsDoctorPopoverOpen] = useState(false);
	const [doctorSearchQuery, setDoctorSearchQuery] = useState("");

	const filteredDoctorOptions = useMemo(() => {
		const q = doctorSearchQuery.toLowerCase().trim();
		if (!q) return doctors;
		return doctors.filter((doc) => doc.toLowerCase().includes(q));
	}, [doctors, doctorSearchQuery]);

	return (
		<div className="flex flex-col gap-3 mb-1">
			{/* Top Row: Search on Left, Filters on Right (consistent with other pages) */}
			<div className="flex items-center justify-between gap-3 flex-wrap">
				<SearchBar
					containerClassName="max-w-md w-full"
					placeholder="Search for notification..."
					value={searchQuery}
					onChange={(e) => onSearchChange(e.target.value)}
				/>

				<div className="flex flex-wrap items-center gap-2">
					{/* Reset Filters button */}
					{hasActiveFilters && (
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={onResetFilters}
							className="text-xs text-red-600 hover:text-red-700 bg-white hover:bg-red-50 border-red-200 hover:border-red-300 rounded-lg cursor-pointer h-10 px-3 gap-1.5 shadow-none transition-colors"
						>
							<RiFilterOffLine className="size-3.5 text-red-500" />
							Reset
						</Button>
					)}

					{/* Searchable Doctor Filter Popover */}
					<Popover open={isDoctorPopoverOpen} onOpenChange={setIsDoctorPopoverOpen}>
						<PopoverTrigger
							render={
								<Button
									variant="outline"
									title={doctorFilter === "ALL" ? "All Doctors" : doctorFilter}
									className="h-10 min-w-36 max-w-52 justify-between gap-1.5 bg-white font-normal text-zinc-700 hover:bg-zinc-50 border-gray-200 text-xs sm:text-sm rounded-lg shadow-none cursor-pointer"
								/>
							}
						>
							<div className="flex items-center gap-1.5 truncate min-w-0">
								<RiUserLine className="size-3.5 shrink-0 text-zinc-500" />
								<span className="truncate">
									{doctorFilter === "ALL" ? "All Doctors" : doctorFilter}
								</span>
							</div>
							<RiArrowDownSLine className="size-3.5 shrink-0 text-zinc-400 ml-1" />
						</PopoverTrigger>
						<PopoverContent
							align="end"
							className="w-56 p-2 flex flex-col gap-2 z-50 bg-white border border-gray-200 shadow-none rounded-lg ring-0 outline-none"
						>
							{/* Search Bar inside Popover */}
							<div className="relative w-full">
								<RiSearchLine className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-zinc-400 pointer-events-none" />
								<Input
									placeholder="Search doctor..."
									value={doctorSearchQuery}
									onChange={(e) => setDoctorSearchQuery(e.target.value)}
									className="h-8 pl-8 pr-7 text-xs bg-zinc-50 border-gray-200 focus-visible:ring-blue-500 rounded-md"
									autoFocus
								/>
								{doctorSearchQuery && (
									<button
										type="button"
										onClick={() => setDoctorSearchQuery("")}
										className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 cursor-pointer"
									>
										<RiCloseLine className="size-3.5" />
									</button>
								)}
							</div>

							{/* Doctor List */}
							<div className="flex flex-col gap-0.5 max-h-56 overflow-y-auto overscroll-contain pr-0.5">
								{(!doctorSearchQuery ||
									"all doctors".includes(doctorSearchQuery.toLowerCase().trim())) && (
									<button
										type="button"
										onClick={() => {
											onDoctorFilterChange("ALL");
											setIsDoctorPopoverOpen(false);
											setDoctorSearchQuery("");
										}}
										className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs font-medium text-left transition-colors cursor-pointer ${
											doctorFilter === "ALL"
												? "bg-blue-50 text-blue-700"
												: "text-zinc-700 hover:bg-zinc-100"
										}`}
									>
										<span className="truncate">All Doctors</span>
										{doctorFilter === "ALL" && (
											<RiCheckLine className="size-3.5 text-blue-600 shrink-0 ml-1.5" />
										)}
									</button>
								)}

								{filteredDoctorOptions.map((doctor) => {
									const isSelected = doctorFilter === doctor;
									return (
										<button
											type="button"
											key={doctor}
											title={doctor}
											onClick={() => {
												onDoctorFilterChange(doctor);
												setIsDoctorPopoverOpen(false);
												setDoctorSearchQuery("");
											}}
											className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs font-medium text-left transition-colors cursor-pointer ${
												isSelected ? "bg-blue-50 text-blue-700" : "text-zinc-700 hover:bg-zinc-100"
											}`}
										>
											<span className="truncate min-w-0 flex-1">{doctor}</span>
											{isSelected && (
												<RiCheckLine className="size-3.5 text-blue-600 shrink-0 ml-1.5" />
											)}
										</button>
									);
								})}

								{filteredDoctorOptions.length === 0 &&
									doctorSearchQuery &&
									!"all doctors".includes(doctorSearchQuery.toLowerCase().trim()) && (
										<div className="py-4 text-center text-xs text-zinc-400">No doctors found</div>
									)}
							</div>
						</PopoverContent>
					</Popover>

					{/* Doctor Type Filter */}
					<DropdownMenu>
						<DropdownMenuTrigger
							render={
								<Button
									variant="outline"
									className="h-10 min-w-36 max-w-52 justify-between gap-1.5 bg-white font-normal text-zinc-700 hover:bg-zinc-50 border-gray-200 text-xs sm:text-sm rounded-lg shadow-none cursor-pointer"
								/>
							}
						>
							<div className="flex items-center gap-1.5 truncate">
								<RiMedicineBottleLine className="size-3.5 shrink-0 text-zinc-500" />
								<span className="truncate">
									{doctorTypeFilter === "ALL" ? "All Doctor Types" : doctorTypeFilter}
								</span>
							</div>
							<RiArrowDownSLine className="size-3.5 shrink-0 text-zinc-400" />
						</DropdownMenuTrigger>
						<DropdownMenuContent
							align="end"
							className="w-52 max-h-56 overflow-y-auto bg-white border border-gray-200 text-xs rounded-lg shadow-none"
						>
							<DropdownMenuRadioGroup
								value={doctorTypeFilter}
								onValueChange={onDoctorTypeFilterChange}
							>
								<DropdownMenuRadioItem closeOnClick value="ALL">
									All Doctor Types
								</DropdownMenuRadioItem>
								{doctorTypes.map((type) => (
									<DropdownMenuRadioItem closeOnClick key={type} value={type}>
										{type}
									</DropdownMenuRadioItem>
								))}
							</DropdownMenuRadioGroup>
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
			</div>

			{/* Bottom Row: Category Tabs (All, Unread, Read) */}
			<div className="flex items-center gap-1">
				<button
					type="button"
					onClick={() => onTabChange("all")}
					className={cn(
						"px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer",
						activeTab === "all"
							? "bg-gray-100 text-gray-900 font-semibold"
							: "text-muted-foreground hover:text-foreground hover:bg-gray-50",
					)}
				>
					All ({totalCount})
				</button>
				<button
					type="button"
					onClick={() => onTabChange("unread")}
					className={cn(
						"px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer",
						activeTab === "unread"
							? "bg-gray-100 text-gray-900 font-semibold"
							: "text-muted-foreground hover:text-foreground hover:bg-gray-50",
					)}
				>
					Unread ({unreadCount})
				</button>
				<button
					type="button"
					onClick={() => onTabChange("read")}
					className={cn(
						"px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer",
						activeTab === "read"
							? "bg-gray-100 text-gray-900 font-semibold"
							: "text-muted-foreground hover:text-foreground hover:bg-gray-50",
					)}
				>
					Read ({readCount})
				</button>
			</div>
		</div>
	);
}
