"use client";

import React, { useState, useMemo } from "react";
import {
	RiSearchLine,
	RiCloseLine,
	RiArrowLeftSLine,
	RiArrowRightSLine,
	RiTableLine,
} from "@remixicon/react";
import { cellPlainText, MarkdownTableCell } from "./elements";

export interface FastMarkdownTableProps {
	headers: string[];
	rows: string[][];
	title?: string;
	initialPageSize?: number;
	onDeleteImage?: (src: string, alt: string) => void;
}

export function FastMarkdownTable({
	headers,
	rows,
	title,
	initialPageSize = 50,
	onDeleteImage,
}: FastMarkdownTableProps) {
	const [page, setPage] = useState(1);
	const [pageSize, setPageSize] = useState(initialPageSize);
	const [search, setSearch] = useState("");

	const filteredRows = useMemo(() => {
		if (!search.trim()) return rows;
		const q = search.toLowerCase().trim();
		return rows.filter((r) => r.some((cell) => cellPlainText(cell).toLowerCase().includes(q)));
	}, [rows, search]);

	const totalRows = filteredRows.length;
	const isLarge = rows.length > 25 || !!search;
	const effectivePageSize = pageSize > 0 ? pageSize : totalRows || 1;
	const totalPages = Math.max(1, Math.ceil(totalRows / effectivePageSize));

	const currentPage = Math.min(Math.max(1, page), totalPages);
	const from = totalRows === 0 ? 0 : (currentPage - 1) * effectivePageSize + 1;
	const to = Math.min(currentPage * effectivePageSize, totalRows);

	const visibleRows = useMemo(() => {
		if (pageSize === 0) return filteredRows;
		const start = (currentPage - 1) * effectivePageSize;
		return filteredRows.slice(start, start + effectivePageSize);
	}, [filteredRows, currentPage, effectivePageSize, pageSize]);

	return (
		<div className="my-3 overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-xs">
			{/* Table Header Bar with Title, Live Search, and Page Size */}
			<div className="flex flex-wrap items-center justify-between gap-3 px-3.5 py-2.5 bg-zinc-50 border-b border-zinc-200 text-xs text-zinc-600">
				<div className="flex items-center gap-2">
					<RiTableLine className="size-4 text-blue-600 shrink-0" />
					<span className="font-semibold text-zinc-800">
						{title || "Tabel Data"} ({rows.length.toLocaleString("id-ID")} baris)
					</span>
					{search && (
						<span className="text-[11px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
							Ditemukan {totalRows.toLocaleString("id-ID")}
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
							className="pl-8 pr-7 py-1 text-xs bg-white border border-zinc-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 w-40 sm:w-56 text-zinc-900"
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

					{isLarge && (
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
					)}
				</div>
			</div>

			{/* Table Content */}
			<div className="overflow-x-auto max-h-[70vh]">
				<table className="min-w-full w-full text-left text-xs sm:text-sm border-collapse divide-y divide-zinc-200">
					<thead className="bg-zinc-100/80 text-zinc-900 font-semibold sticky top-0 z-10 shadow-xs">
						<tr>
							{headers.map((h, idx) => (
								<th
									key={idx}
									className="px-3.5 py-2 font-semibold text-zinc-900 border-r border-zinc-200/60 last:border-r-0 whitespace-nowrap bg-zinc-100 min-w-[90px]"
								>
									<MarkdownTableCell content={h} />
								</th>
							))}
						</tr>
					</thead>
					<tbody className="divide-y divide-zinc-100 bg-white">
						{visibleRows.length === 0 ? (
							<tr>
								<td
									colSpan={headers.length || 1}
									className="py-10 text-center text-xs text-zinc-500 italic bg-zinc-50/50"
								>
									Tidak ada data yang cocok dengan pencarian &quot;{search}&quot;
								</td>
							</tr>
						) : (
							visibleRows.map((row, rIdx) => (
								<tr
									key={rIdx}
									className="hover:bg-blue-50/40 transition-colors odd:bg-white even:bg-zinc-50/30"
								>
									{row.map((cell, cIdx) => (
										<td
											key={cIdx}
											className="px-3.5 py-2 text-zinc-800 font-normal border-r border-zinc-100 last:border-r-0 text-xs sm:text-[13px] leading-relaxed min-w-[110px] align-top"
										>
											<MarkdownTableCell content={cell} onDeleteImage={onDeleteImage} />
										</td>
									))}
								</tr>
							))
						)}
					</tbody>
				</table>
			</div>

			{/* Pagination Footer */}
			{isLarge && totalPages > 1 && (
				<div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2 bg-zinc-50 border-t border-zinc-200 text-xs text-zinc-600">
					<div>
						Menampilkan <span className="font-semibold text-zinc-800">{from}</span>–
						<span className="font-semibold text-zinc-800">{to}</span> dari{" "}
						<span className="font-semibold text-zinc-800">
							{totalRows.toLocaleString("id-ID")}
						</span>{" "}
						baris
					</div>

					<div className="flex items-center gap-1.5 ml-auto">
						<button
							type="button"
							disabled={currentPage <= 1}
							onClick={() => setPage((p) => Math.max(1, p - 1))}
							className="p-1 rounded border border-zinc-200 bg-white text-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-100 transition-colors cursor-pointer"
							title="Halaman Sebelumnya"
						>
							<RiArrowLeftSLine className="size-4" />
						</button>

						<span className="px-2 font-medium text-zinc-700">
							Halaman {currentPage} dari {totalPages}
						</span>

						<button
							type="button"
							disabled={currentPage >= totalPages}
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
	);
}
