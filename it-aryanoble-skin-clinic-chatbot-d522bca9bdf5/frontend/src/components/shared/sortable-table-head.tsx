"use client";

import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { RiArrowDownSLine, RiArrowUpSLine, RiExpandUpDownLine } from "@remixicon/react";
import * as React from "react";

export type SortOrder = "asc" | "desc" | null;

interface SortableTableHeadProps extends React.ComponentProps<typeof TableHead> {
	sortKey: string;
	currentSortKey?: string | null;
	sortOrder?: SortOrder;
	onSort?: (key: string) => void;
	align?: "left" | "right" | "center";
}

export function SortableTableHead({
	sortKey,
	currentSortKey,
	sortOrder,
	onSort,
	align = "left",
	className,
	children,
	...props
}: SortableTableHeadProps) {
	const isActive = currentSortKey === sortKey && sortOrder !== null;

	const handleClick = () => {
		if (onSort) {
			onSort(sortKey);
		}
	};

	const handleKeyDown = (e: React.KeyboardEvent) => {
		if (e.key === "Enter" || e.key === " ") {
			e.preventDefault();
			if (onSort) {
				onSort(sortKey);
			}
		}
	};

	return (
		<TableHead
			className={cn(
				"cursor-pointer select-none group transition-colors hover:text-gray-900",
				isActive && "text-blue-600 font-semibold",
				className,
			)}
			onClick={handleClick}
			onKeyDown={handleKeyDown}
			tabIndex={0}
			role="columnheader"
			aria-sort={isActive ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}
			{...props}
		>
			<div
				className={cn(
					"inline-flex items-center gap-1",
					align === "right" && "justify-end w-full",
					align === "center" && "justify-center w-full",
				)}
			>
				<span>{children}</span>
				<span className="inline-flex items-center text-xs shrink-0">
					{isActive ? (
						sortOrder === "asc" ? (
							<RiArrowUpSLine className="w-4 h-4 text-blue-600" aria-label="Sorted ascending" />
						) : (
							<RiArrowDownSLine className="w-4 h-4 text-blue-600" aria-label="Sorted descending" />
						)
					) : (
						<RiExpandUpDownLine
							className="w-3.5 h-3.5 text-gray-400 opacity-60 group-hover:opacity-100 transition-opacity"
							aria-label="Sort column"
						/>
					)}
				</span>
			</div>
		</TableHead>
	);
}
