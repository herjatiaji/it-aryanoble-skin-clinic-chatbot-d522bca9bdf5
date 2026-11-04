"use client";

import React, { createContext, useContext, useState, useMemo, useEffect, ReactNode } from "react";
import {
	RiSearchLine,
	RiCloseLine,
	RiArrowLeftSLine,
	RiArrowRightSLine,
	RiTableLine,
} from "@remixicon/react";

interface TableContextType {
	page: number;
	setPage: React.Dispatch<React.SetStateAction<number>>;
	pageSize: number;
	setPageSize: (size: number) => void;
	search: string;
	setSearch: (q: string) => void;
	rowCount: number;
	setRowCount: (count: number) => void;
	filteredCount: number;
	setFilteredCount: (count: number) => void;
}

const TableContext = createContext<TableContextType | null>(null);

function extractRowText(node: unknown): string {
	if (!node) return "";
	if (typeof node === "string" || typeof node === "number") return String(node);
	if (Array.isArray(node)) return node.map(extractRowText).join(" ");
	if (React.isValidElement(node)) {
		const props = node.props as { children?: unknown };
		if (props && props.children) {
			return extractRowText(props.children);
		}
	}
	return "";
}

export function MarkdownTable({ children, ...props }: React.ComponentProps<"table">) {
	const [page, setPage] = useState(1);
	const [pageSize, setPageSize] = useState(25);
	const [search, setSearch] = useState("");
	const [rowCount, setRowCount] = useState(0);
	const [filteredCount, setFilteredCount] = useState(0);

	const isLargeTable = rowCount > 20 || !!search;
	const activeTotal = search ? filteredCount : rowCount;
	const effectivePageSize = pageSize > 0 ? pageSize : activeTotal || 1;
	const totalPages = Math.max(1, Math.ceil(activeTotal / effectivePageSize));

	const from = activeTotal === 0 ? 0 : (page - 1) * effectivePageSize + 1;
	const to = Math.min(page * effectivePageSize, activeTotal);

	const contextValue = useMemo<TableContextType>(
		() => ({
			page,
			setPage,
			pageSize,
			setPageSize,
			search,
			setSearch,
			rowCount,
			setRowCount,
			filteredCount,
			setFilteredCount,
		}),
		[page, pageSize, search, rowCount, filteredCount],
	);

	return (
		<TableContext.Provider value={contextValue}>
			<div className="my-2.5 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-xs">
				{isLargeTable && (
					<div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-zinc-50 border-b border-zinc-200 text-xs text-zinc-600">
						<div className="flex items-center gap-2">
							<RiTableLine className="size-4 text-blue-600 shrink-0" />
							<span className="font-semibold text-zinc-800">
								Tabel Data ({rowCount.toLocaleString("id-ID")} baris)
							</span>
							{search && (
								<span className="text-[11px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
									Ditemukan {filteredCount.toLocaleString("id-ID")}
								</span>
							)}
						</div>

						<div className="flex items-center gap-2 ml-auto">
							<div className="relative flex items-center">
								<RiSearchLine className="size-3.5 text-zinc-400 absolute left-2.5 pointer-events-none" />
								<input
									type="text"
									value={search}
									onChange={(e) => {
										setSearch(e.target.value);
										setPage(1);
									}}
									placeholder="Cari dalam tabel..."
									className="pl-8 pr-7 py-1 text-xs bg-white border border-zinc-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 w-44 sm:w-56 text-zinc-900"
								/>
								{search && (
									<button
										type="button"
										onClick={() => {
											setSearch("");
											setPage(1);
										}}
										className="absolute right-2 text-zinc-400 hover:text-zinc-600 cursor-pointer"
										title="Hapus pencarian"
									>
										<RiCloseLine className="size-3.5" />
									</button>
								)}
							</div>

							<select
								value={pageSize}
								onChange={(e) => {
									setPageSize(Number(e.target.value));
									setPage(1);
								}}
								className="px-2 py-1 text-xs bg-white border border-zinc-200 rounded-md text-zinc-700 focus:outline-none cursor-pointer"
							>
								<option value={25}>25 / hal</option>
								<option value={50}>50 / hal</option>
								<option value={100}>100 / hal</option>
								<option value={0}>Semua</option>
							</select>
						</div>
					</div>
				)}

				<div className="overflow-x-auto">
					<table
						className="min-w-full w-full text-left text-xs sm:text-sm border-collapse divide-y divide-zinc-200"
						{...props}
					>
						{children}
					</table>
				</div>

				{isLargeTable && totalPages > 1 && (
					<div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-zinc-50 border-t border-zinc-200 text-xs text-zinc-600">
						<div>
							Menampilkan <span className="font-semibold text-zinc-800">{from}</span>–
							<span className="font-semibold text-zinc-800">{to}</span> dari{" "}
							<span className="font-semibold text-zinc-800">{activeTotal.toLocaleString("id-ID")}</span> baris
						</div>

						<div className="flex items-center gap-1.5 ml-auto">
							<button
								type="button"
								disabled={page <= 1}
								onClick={() => setPage((p) => Math.max(1, p - 1))}
								className="p-1 rounded border border-zinc-200 bg-white text-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-100 transition-colors cursor-pointer"
								title="Halaman Sebelumnya"
							>
								<RiArrowLeftSLine className="size-4" />
							</button>

							<span className="px-2 font-medium text-zinc-700">
								Halaman {page} dari {totalPages}
							</span>

							<button
								type="button"
								disabled={page >= totalPages}
								onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
								className="p-1 rounded border border-zinc-200 bg-white text-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-100 transition-colors cursor-pointer"
								title="Halaman Berikutnya"
							>
								<RiArrowRightSLine className="size-4" />
							</button>
						</div>
					</div>
				)}
			</div>
		</TableContext.Provider>
	);
}

export function MarkdownTbody({ children, ...props }: React.ComponentProps<"tbody">) {
	const tableCtx = useContext(TableContext);
	const rows = useMemo(() => React.Children.toArray(children), [children]);

	const { page = 1, pageSize = 50, search = "", setRowCount, setFilteredCount } = tableCtx || {};

	useEffect(() => {
		setRowCount?.(rows.length);
	}, [rows.length, setRowCount]);

	const filteredRows = useMemo(() => {
		if (!search.trim()) return rows;
		const query = search.toLowerCase();
		return rows.filter((r) => extractRowText(r).toLowerCase().includes(query));
	}, [rows, search]);

	useEffect(() => {
		if (tableCtx?.search) {
			setFilteredCount?.(filteredRows.length);
		}
	}, [filteredRows.length, tableCtx?.search, setFilteredCount]);

	if (!tableCtx || (rows.length <= 20 && !search)) {
		return (
			<tbody className="divide-y divide-zinc-100 bg-white" {...props}>
				{children}
			</tbody>
		);
	}

	const effectivePageSize = pageSize > 0 ? pageSize : filteredRows.length || 1;
	const startIndex = (page - 1) * effectivePageSize;
	const visibleRows = pageSize === 0 ? filteredRows : filteredRows.slice(startIndex, startIndex + effectivePageSize);

	if (filteredRows.length === 0) {
		return (
			<tbody className="divide-y divide-zinc-100 bg-white" {...props}>
				<tr>
					<td colSpan={100} className="py-8 text-center text-xs text-zinc-500 italic bg-zinc-50/50">
						Tidak ada data yang cocok dengan pencarian &quot;{search}&quot;
					</td>
				</tr>
			</tbody>
		);
	}

	return (
		<tbody className="divide-y divide-zinc-100 bg-white" {...props}>
			{visibleRows}
		</tbody>
	);
}
