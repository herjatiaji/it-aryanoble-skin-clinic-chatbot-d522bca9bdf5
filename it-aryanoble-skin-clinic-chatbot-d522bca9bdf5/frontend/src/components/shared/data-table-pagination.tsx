"use client";

import { Button } from "@/components/ui/button";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	RiArrowLeftSLine,
	RiArrowRightSLine,
	RiMoreLine,
} from "@remixicon/react";
import { useMemo } from "react";
import { calculatePaginationRange, formatItemName } from "./pagination-utils";

export interface DataTablePaginationProps {
	page: number;
	pageSize: number;
	totalPages: number;
	totalItems: number;
	startIndex: number;
	endIndex: number;
	onPageChange: (page: number) => void;
	onPageSizeChange?: (size: number) => void;
	pageSizeOptions?: number[];
	itemName?: string;
	showPageSize?: boolean;
}

export function DataTablePagination({
	page,
	pageSize,
	totalPages,
	totalItems,
	startIndex,
	endIndex,
	onPageChange,
	onPageSizeChange,
	pageSizeOptions = [10, 20, 50, 100],
	itemName = "results",
	showPageSize = true,
}: DataTablePaginationProps) {
	const paginationRange = useMemo(
		() => calculatePaginationRange(page, totalPages),
		[page, totalPages],
	);

	const summaryContent = useMemo(() => {
		const singleName = formatItemName(itemName, 1);
		const pluralName = formatItemName(itemName, totalItems);

		if (totalItems === 1) {
			return (
				<>
					Showing <span className="font-semibold text-zinc-900">1</span> {singleName}
				</>
			);
		}

		if (startIndex === 1 && endIndex === totalItems) {
			return (
				<>
					Showing all <span className="font-semibold text-zinc-900">{totalItems}</span> {pluralName}
				</>
			);
		}

		if (startIndex === endIndex) {
			return (
				<>
					Showing <span className="font-semibold text-zinc-900">{startIndex}</span> of{" "}
					<span className="font-semibold text-zinc-900">{totalItems}</span> {pluralName}
				</>
			);
		}

		return (
			<>
				Showing <span className="font-semibold text-zinc-900">{startIndex}</span>–
				<span className="font-semibold text-zinc-900">{endIndex}</span> of{" "}
				<span className="font-semibold text-zinc-900">{totalItems}</span> {pluralName}
			</>
		);
	}, [startIndex, endIndex, totalItems, itemName]);

	if (totalItems === 0) {
		return null;
	}

	return (
		<div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-3 px-1 text-sm text-zinc-600">
			{/* Left: Summary text */}
			<div className="text-xs text-zinc-500 order-2 sm:order-1 select-none">
				{summaryContent}
			</div>

			{/* Right: Controls (Page size + Page buttons) */}
			<div className="flex items-center gap-4 order-1 sm:order-2 flex-wrap justify-center sm:justify-end">
				{showPageSize && onPageSizeChange && (
					<div className="flex items-center gap-2 text-xs text-zinc-500">
						<span>Rows per page:</span>
						<Select
							value={String(pageSize)}
							onValueChange={(val) => {
								if (val) onPageSizeChange(Number(val));
							}}
						>
							<SelectTrigger className="h-8 w-18 px-2.5 text-xs bg-white border-gray-200 text-zinc-800 hover:border-blue-300 focus-visible:ring-blue-500 rounded-md transition-colors">
								<SelectValue placeholder={String(pageSize)}>
									{String(pageSize)}
								</SelectValue>
							</SelectTrigger>
							<SelectContent align="end" alignItemWithTrigger={false} sideOffset={4} className="bg-white">
								{pageSizeOptions.map((size) => (
									<SelectItem key={size} value={String(size)} className="text-xs">
										{size}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</div>
				)}

				<div className="flex items-center gap-1">
					{/* Previous button */}
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={() => onPageChange(page - 1)}
						disabled={page <= 1}
						className="h-8 px-2.5 text-xs border-gray-200 bg-white text-zinc-700 hover:bg-blue-50/60 hover:text-blue-600 hover:border-blue-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:text-zinc-700 disabled:hover:border-gray-200 shadow-none gap-1"
					>
						<RiArrowLeftSLine className="size-4" />
						<span className="hidden xs:inline">Prev</span>
					</Button>

					{/* Numbered Page Buttons */}
					<div className="hidden sm:flex items-center gap-1">
						{paginationRange.map((item, index) => {
							if (typeof item === "string") {
								return (
									<span
										key={`ellipsis-${index}`}
										className="flex size-8 items-center justify-center text-zinc-400"
									>
										<RiMoreLine className="size-3.5" />
									</span>
								);
							}

							const isCurrent = item === page;

							return (
								<Button
									key={item}
									type="button"
									variant={isCurrent ? "default" : "ghost"}
									size="icon"
									onClick={() => onPageChange(item)}
									className={`size-8 text-xs font-semibold rounded-md shadow-none transition-colors ${
										isCurrent
											? "bg-blue-600 text-white hover:bg-blue-700 shadow-xs"
											: "text-zinc-600 hover:bg-blue-50 hover:text-blue-600"
									}`}
								>
									{item}
								</Button>
							);
						})}
					</div>

					{/* Mobile Page Indicator */}
					<span className="sm:hidden text-xs text-zinc-600 px-2 font-medium">
						{page} / {totalPages}
					</span>

					{/* Next button */}
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={() => onPageChange(page + 1)}
						disabled={page >= totalPages}
						className="h-8 px-2.5 text-xs border-gray-200 bg-white text-zinc-700 hover:bg-blue-50/60 hover:text-blue-600 hover:border-blue-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:text-zinc-700 disabled:hover:border-gray-200 shadow-none gap-1"
					>
						<span className="hidden xs:inline">Next</span>
						<RiArrowRightSLine className="size-4" />
					</Button>
				</div>
			</div>
		</div>
	);
}
