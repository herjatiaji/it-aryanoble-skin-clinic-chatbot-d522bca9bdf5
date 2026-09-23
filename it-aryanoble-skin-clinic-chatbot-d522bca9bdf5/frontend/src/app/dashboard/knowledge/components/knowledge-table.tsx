"use client";

import { useCategories } from "@/app/dashboard/category/hooks/use-categories";
import { KnowledgeResponse, extractKnowledgeCategories } from "@/app/dashboard/knowledge/api/types";
import {
	useDeleteKnowledge,
	useKnowledgeBaseList,
} from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { stripMarkdown } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { DataTablePagination } from "@/components/shared/data-table-pagination";
import { SortableTableHead } from "@/components/shared/sortable-table-head";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuRadioGroup,
	DropdownMenuRadioItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { usePagination } from "@/hooks/use-pagination";
import { useTableSort } from "@/hooks/use-table-sort";
import {
	RiArrowDownSLine,
	RiBookOpenLine,
	RiBookletLine,
	RiCheckLine,
	RiCloseLine,
	RiDatabase2Line,
	RiDeleteBinLine,
	RiEdit2Line,
	RiEyeLine,
	RiFilterOffLine,
	RiLoader4Line,
	RiMoneyDollarCircleLine,
	RiMore2Line,
	RiSearchLine,
} from "@remixicon/react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { AttachProjectDialog } from "./attach-project-dialog";

interface DisplayRowItem {
	id: string;
	isBatch: boolean;
	batchId?: string;
	title: string;
	status: string;
	created_at?: string;
	approved_at?: string | null;
	uploadedByName?: string | null;
	description: string;
	documentCount?: number;
	rawItem: KnowledgeResponse;
	allFileNames: string[];
	categories: string[];
	projectId?: string | null;
	allDocIds?: string[];
}

interface KnowledgeTableProps {
	searchQuery?: string;
	selectedProjectId?: string | null;
	onClearProjectFilter?: () => void;
}

export function KnowledgeTable({
	searchQuery = "",
	selectedProjectId,
	onClearProjectFilter,
}: KnowledgeTableProps) {
	const router = useRouter();
	const [statusFilter, setStatusFilter] = useState("ALL");
	const [categoryFilter, setCategoryFilter] = useState("ALL");
	const [isCategoryPopoverOpen, setIsCategoryPopoverOpen] = useState(false);
	const [categorySearchQuery, setCategorySearchQuery] = useState("");
	const { data: knowledgeList, isLoading, isError } = useKnowledgeBaseList();
	const { data: availableCategories = [] } = useCategories();
	const deleteMutation = useDeleteKnowledge();

	const filteredAvailableCategories = useMemo(() => {
		if (!categorySearchQuery.trim()) return availableCategories;
		const q = categorySearchQuery.toLowerCase().trim();
		return availableCategories.filter((c) => c.name.toLowerCase().includes(q));
	}, [availableCategories, categorySearchQuery]);

	// Delete Confirmation Modal State
	const [deleteModalOpen, setDeleteModalOpen] = useState(false);
	const [itemToDelete, setItemToDelete] = useState<DisplayRowItem | null>(null);

	// Bulk Delete Selection State
	const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
	const [isBulkDeleteModalOpen, setIsBulkDeleteModalOpen] = useState(false);
	const [isBulkDeleting, setIsBulkDeleting] = useState(false);

	// Attach Project Modal State
	const [isAttachModalOpen, setIsAttachModalOpen] = useState(false);
	const [attachKnowledgeId, setAttachKnowledgeId] = useState<string | null>(null);
	const [attachKnowledgeIds, setAttachKnowledgeIds] = useState<string[] | undefined>(undefined);
	const [attachKnowledgeTitle, setAttachKnowledgeTitle] = useState("");
	const [attachCurrentProjectId, setAttachCurrentProjectId] = useState<string | null>(null);

	const basePath = "/dashboard/knowledge";

	const handleDeleteClick = (row: DisplayRowItem, e: React.MouseEvent) => {
		e.stopPropagation();
		setItemToDelete(row);
		setDeleteModalOpen(true);
	};

	const handleConfirmDelete = async () => {
		if (itemToDelete) {
			const idsToDelete =
				itemToDelete.allDocIds && itemToDelete.allDocIds.length > 0
					? itemToDelete.allDocIds
					: [itemToDelete.id];

			try {
				if (idsToDelete.length > 1) {
					await Promise.all(
						idsToDelete.map((id) => deleteMutation.mutateAsync({ id, hideToast: true })),
					);
					toast.success(`All ${idsToDelete.length} documents deleted successfully!`);
				} else {
					await deleteMutation.mutateAsync(idsToDelete[0]);
				}
			} catch {
				// handled by mutation
			}
			setDeleteModalOpen(false);
			setItemToDelete(null);
		}
	};

	const handleRowClick = (row: DisplayRowItem) => {
		if (row.isBatch && row.batchId) {
			router.push(`${basePath}/batch/${row.batchId}`);
		} else {
			router.push(`${basePath}/${row.id}`);
		}
	};

	const isCategoryMatch = (itemCategories: string[], filterCat: string) => {
		if (!filterCat || filterCat === "ALL") return true;
		const target = filterCat.toLowerCase();
		return itemCategories.some(
			(c) => c.toLowerCase() === target || c.toLowerCase().includes(target),
		);
	};

	// Group knowledgeList by batch_id if present and collect categories
	const displayRows = useMemo<DisplayRowItem[]>(() => {
		if (!knowledgeList) return [];

		const batchMap = new Map<string, KnowledgeResponse[]>();
		const singleItems: KnowledgeResponse[] = [];

		for (const item of knowledgeList) {
			const bId = (item.metadata?.batch_id || item.metadata?.upload_batch_id) as string | undefined;
			if (bId) {
				const existing = batchMap.get(bId) || [];
				existing.push(item);
				batchMap.set(bId, existing);
			} else {
				singleItems.push(item);
			}
		}

		const rows: DisplayRowItem[] = [];

		// 1. Process Batch Groups
		for (const [batchId, docs] of batchMap.entries()) {
			const combinedCategories = Array.from(
				new Set(docs.flatMap((d) => extractKnowledgeCategories(d))),
			);

			if (docs.length === 1) {
				const doc = docs[0];
				rows.push({
					id: doc.id,
					isBatch: true,
					batchId,
					title: doc.title || doc.file_name,
					status: doc.status,
					created_at: doc.created_at,
					approved_at: doc.approved_at,
					uploadedByName: doc.uploaded_by_name || "Admin",
					description: stripMarkdown(doc.ai_summary || doc.content) || "No description available.",
					documentCount: 1,
					rawItem: doc,
					allFileNames: [doc.file_name],
					categories: combinedCategories,
					projectId: doc.project_id,
					allDocIds: [doc.id],
				});
			} else {
				let aggStatus = "APPROVED";
				const hasProcessing = docs.some((d) => d.status === "PROCESSING");
				const hasPending = docs.some((d) => d.status === "PENDING");
				const hasRejected = docs.some((d) => d.status === "REJECTED");

				if (hasProcessing) {
					aggStatus = "PROCESSING";
				} else if (hasPending) {
					aggStatus = "PENDING";
				} else if (docs.every((d) => d.status === "APPROVED")) {
					aggStatus = "APPROVED";
				} else if (hasRejected) {
					aggStatus = "REJECTED";
				} else {
					aggStatus = docs[0].status;
				}

				const batchSummary =
					(docs[0].metadata?.batch_summary as string) || docs[0].ai_summary || "";
				const allNames = docs.map((d) => d.file_name || d.title);
				const firstDocTitle = docs[0].title || docs[0].file_name;
				const displayTitle = `${firstDocTitle} + ${docs.length - 1} more`;

				const mostRecentDate = docs.reduce((latest, d) => {
					if (!latest) return d.created_at;
					if (!d.created_at) return latest;
					return new Date(d.created_at) > new Date(latest) ? d.created_at : latest;
				}, docs[0].created_at);

				const uploader =
					docs.find((d) => Boolean(d.uploaded_by_name))?.uploaded_by_name ||
					docs[0].uploaded_by_name ||
					"Admin";
				const mostRecentApprovedAt = docs.reduce((latest, d) => {
					if (!latest) return d.approved_at;
					if (!d.approved_at) return latest;
					return new Date(d.approved_at) > new Date(latest) ? d.approved_at : latest;
				}, docs[0].approved_at);

				// Determine batch projectId: if any doc in batch has projectId
				const batchProjectId = docs.find((d) => Boolean(d.project_id))?.project_id || null;

				rows.push({
					id: docs[0].id,
					isBatch: true,
					batchId,
					title: displayTitle,
					status: aggStatus,
					created_at: mostRecentDate,
					approved_at: mostRecentApprovedAt,
					uploadedByName: uploader,
					description: stripMarkdown(batchSummary) || `Batch upload containing ${docs.length} documents.`,
					documentCount: docs.length,
					rawItem: docs[0],
					allFileNames: allNames,
					categories: combinedCategories,
					projectId: batchProjectId,
					allDocIds: docs.map((d) => d.id),
				});
			}
		}

		// 2. Process Standalone Items
		for (const doc of singleItems) {
			rows.push({
				id: doc.id,
				isBatch: false,
				title: doc.title || doc.file_name,
				status: doc.status,
				created_at: doc.created_at,
				approved_at: doc.approved_at,
				uploadedByName: doc.uploaded_by_name || "Admin",
				description: stripMarkdown(doc.ai_summary || doc.content) || "No description available.",
				documentCount: 1,
				rawItem: doc,
				allFileNames: [doc.file_name],
				categories: extractKnowledgeCategories(doc),
				projectId: doc.project_id,
				allDocIds: [doc.id],
			});
		}

		return rows;
	}, [knowledgeList]);

	const { sortKey, sortOrder, handleSort, sortItems } = useTableSort({
		initialSortKey: "created_at",
		initialSortOrder: "desc",
	});

	const filteredList = useMemo(() => {
		const result = (displayRows || [])
			.filter((item) => (selectedProjectId ? item.projectId === selectedProjectId : true))
			.filter((item) => (statusFilter !== "ALL" ? item.status === statusFilter : true))
			.filter((item) => isCategoryMatch(item.categories, categoryFilter))
			.filter(
				(item) =>
					item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
					item.allFileNames.some((f) => f.toLowerCase().includes(searchQuery.toLowerCase())) ||
					item.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
					item.categories.some((c) => c.toLowerCase().includes(searchQuery.toLowerCase())) ||
					(item.uploadedByName && item.uploadedByName.toLowerCase().includes(searchQuery.toLowerCase())),
			);

		return sortItems<DisplayRowItem>(result);
	}, [displayRows, selectedProjectId, statusFilter, categoryFilter, searchQuery, sortItems]);

	const {
		page,
		pageSize,
		totalPages,
		totalItems,
		paginatedItems,
		setPage,
		setPageSize,
		startIndex,
		endIndex,
	} = usePagination<DisplayRowItem>({ items: filteredList, initialPageSize: 10 });

	const currentPageDocIds = useMemo(() => {
		return paginatedItems.flatMap((item) =>
			item.allDocIds && item.allDocIds.length > 0 ? item.allDocIds : [item.id],
		);
	}, [paginatedItems]);

	const isAllCurrentPageSelected = useMemo(() => {
		if (currentPageDocIds.length === 0) return false;
		return currentPageDocIds.every((id) => selectedIds.has(id));
	}, [currentPageDocIds, selectedIds]);

	const handleSelectAllCurrentPage = () => {
		setSelectedIds((prev) => {
			const next = new Set(prev);
			if (isAllCurrentPageSelected) {
				currentPageDocIds.forEach((id) => next.delete(id));
			} else {
				currentPageDocIds.forEach((id) => next.add(id));
			}
			return next;
		});
	};

	const handleConfirmBulkDelete = async () => {
		const ids = Array.from(selectedIds);
		if (ids.length === 0) return;

		setIsBulkDeleting(true);
		try {
			await Promise.all(
				ids.map((id) => deleteMutation.mutateAsync({ id, hideToast: true })),
			);
			toast.success(`Successfully deleted ${ids.length} documents!`);
			setSelectedIds(new Set());
		} catch {
			toast.error("An error occurred while deleting selected documents.");
		} finally {
			setIsBulkDeleting(false);
			setIsBulkDeleteModalOpen(false);
		}
	};

	const hasActiveFilters =
		statusFilter !== "ALL" || categoryFilter !== "ALL" || !!selectedProjectId;

	const handleResetFilters = () => {
		setStatusFilter("ALL");
		setCategoryFilter("ALL");
		setCategorySearchQuery("");
		setPage(1);
		if (onClearProjectFilter) onClearProjectFilter();
	};

	const getStatusBadge = (status: string) => {
		switch (status) {
			case "APPROVED":
				return (
					<Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-50">
						APPROVED
					</Badge>
				);
			case "PENDING":
				return (
					<Badge className="bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-50">
						PENDING
					</Badge>
				);
			case "PROCESSING":
				return (
					<Badge className="bg-blue-50 text-blue-700 border-blue-200 animate-pulse hover:bg-blue-50">
						PROCESSING
					</Badge>
				);
			case "REJECTED":
				return (
					<Badge className="bg-red-50 text-red-700 border-red-200 hover:bg-red-50">REJECTED</Badge>
				);
			default:
				return <Badge variant="secondary">{status}</Badge>;
		}
	};

	return (
		<div className="w-full">
			{/* Header / Filters Bar */}
			<div className="flex flex-wrap items-center justify-between gap-3 mb-3">
				<h3 className="text-base font-semibold text-gray-900">Knowledge List</h3>

				<div className="flex flex-wrap items-center gap-2.5">
					{/* Active Project Filter Badge */}
					{selectedProjectId && (
						<div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-blue-50 border border-blue-200 text-xs font-medium text-blue-700">
							<span>Project Filter Active</span>
							<button
								type="button"
								onClick={onClearProjectFilter}
								className="hover:text-blue-900 cursor-pointer"
							>
								<RiCloseLine className="size-3.5" />
							</button>
						</div>
					)}

					{/* Reset Filters button */}
					{hasActiveFilters && (
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={handleResetFilters}
							className="text-xs text-red-600 hover:text-red-700 bg-white hover:bg-red-50 border-red-200 hover:border-red-300 rounded-lg cursor-pointer h-9 px-3 gap-1.5 shadow-none transition-colors"
						>
							<RiFilterOffLine className="size-3.5 text-red-500" />
							Reset
						</Button>
					)}

					{/* Category Filter with Search */}
					<Popover open={isCategoryPopoverOpen} onOpenChange={setIsCategoryPopoverOpen}>
						<PopoverTrigger
							render={
								<Button
									variant="outline"
									title={categoryFilter === "ALL" ? "All Categories" : categoryFilter}
									className="min-w-44 h-10 justify-between gap-2 bg-white font-normal text-zinc-700 hover:bg-zinc-50 border-gray-200 rounded-lg text-sm shadow-none cursor-pointer"
								/>
							}
						>
							<div className="flex items-center gap-2 min-w-0 flex-1">
								<RiDatabase2Line className="size-4 shrink-0 text-gray-500" />
								<span className="truncate text-left">
									{categoryFilter === "ALL" ? "All Categories" : categoryFilter}
								</span>
							</div>
							<RiArrowDownSLine className="size-4 shrink-0 text-zinc-400 ml-1" />
						</PopoverTrigger>
						<PopoverContent
							align="start"
							className="w-56 p-2 flex flex-col gap-2 z-50 bg-white border border-gray-200 shadow-none rounded-lg ring-0 outline-none"
						>
							{/* Search Bar inside Popover */}
							<div className="relative w-full">
								<RiSearchLine className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-zinc-400 pointer-events-none" />
								<Input
									placeholder="Search category..."
									value={categorySearchQuery}
									onChange={(e) => setCategorySearchQuery(e.target.value)}
									className="h-8 pl-8 pr-7 text-xs bg-zinc-50 border-gray-200 focus-visible:ring-blue-500 rounded-md"
									autoFocus
								/>
								{categorySearchQuery && (
									<button
										type="button"
										onClick={() => setCategorySearchQuery("")}
										className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 cursor-pointer"
									>
										<RiCloseLine className="size-3.5" />
									</button>
								)}
							</div>

							{/* Category List */}
							<div className="flex flex-col gap-0.5 max-h-56 overflow-y-auto overscroll-contain pr-0.5">
								{(!categorySearchQuery ||
									"all categories".includes(categorySearchQuery.toLowerCase().trim())) && (
									<button
										type="button"
										onClick={() => {
											setCategoryFilter("ALL");
											setIsCategoryPopoverOpen(false);
											setCategorySearchQuery("");
											setPage(1);
										}}
										className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs font-medium text-left transition-colors cursor-pointer ${
											categoryFilter === "ALL"
												? "bg-blue-50 text-blue-700"
												: "text-zinc-700 hover:bg-zinc-100"
										}`}
									>
										<span className="truncate">All Categories</span>
										{categoryFilter === "ALL" && (
											<RiCheckLine className="size-3.5 text-blue-600 shrink-0 ml-1.5" />
										)}
									</button>
								)}

								{filteredAvailableCategories.map((cat) => {
									const isSelected = categoryFilter === cat.name;
									return (
										<button
											type="button"
											key={cat.id}
											title={cat.name}
											onClick={() => {
												setCategoryFilter(cat.name);
												setIsCategoryPopoverOpen(false);
												setCategorySearchQuery("");
												setPage(1);
											}}
											className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs font-medium text-left transition-colors cursor-pointer ${
												isSelected ? "bg-blue-50 text-blue-700" : "text-zinc-700 hover:bg-zinc-100"
											}`}
										>
											<span className="truncate min-w-0 flex-1">{cat.name}</span>
											{isSelected && (
												<RiCheckLine className="size-3.5 text-blue-600 shrink-0 ml-1.5" />
											)}
										</button>
									);
								})}

								{filteredAvailableCategories.length === 0 &&
									categorySearchQuery &&
									!"all categories".includes(categorySearchQuery.toLowerCase().trim()) && (
										<div className="py-4 text-center text-xs text-zinc-400">
											No categories found
										</div>
									)}
							</div>
						</PopoverContent>
					</Popover>

					{/* Status Filter */}
					<DropdownMenu>
						<DropdownMenuTrigger
							render={
								<Button
									variant="outline"
									className="min-w-36 h-10 justify-start gap-2 bg-white font-normal text-zinc-700 hover:bg-zinc-50 border-gray-200 rounded-lg text-sm shadow-none cursor-pointer"
								/>
							}
						>
							<RiMoneyDollarCircleLine className="size-4 shrink-0 text-gray-500" />
							<span className="truncate">
								{statusFilter === "ALL"
									? "All Status"
									: statusFilter.charAt(0) + statusFilter.slice(1).toLowerCase()}
							</span>
						</DropdownMenuTrigger>
						<DropdownMenuContent className="w-44 rounded-lg border border-gray-200 shadow-none p-1 bg-white">
							<DropdownMenuRadioGroup value={statusFilter} onValueChange={setStatusFilter}>
								<DropdownMenuRadioItem closeOnClick value="ALL">
									All Status
								</DropdownMenuRadioItem>
								<DropdownMenuRadioItem closeOnClick value="APPROVED">
									Approved
								</DropdownMenuRadioItem>
								<DropdownMenuRadioItem closeOnClick value="PENDING">
									Pending
								</DropdownMenuRadioItem>
								<DropdownMenuRadioItem closeOnClick value="PROCESSING">
									Processing
								</DropdownMenuRadioItem>
							</DropdownMenuRadioGroup>
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
			</div>

			{/* Bulk Action Floating Bar */}
			{selectedIds.size > 0 && (
				<div className="flex items-center justify-between gap-3 px-4 py-2.5 mb-3 bg-blue-50/80 border border-blue-200 rounded-lg animate-in fade-in slide-in-from-top-2 duration-200">
					<div className="flex items-center gap-2">
						<span className="text-xs font-semibold text-blue-900 bg-blue-200/80 px-2 py-0.5 rounded-full">
							{selectedIds.size} selected
						</span>
						<span className="text-xs text-blue-800">documents selected across the knowledge base</span>
					</div>
					<div className="flex items-center gap-2">
						<Button
							variant="ghost"
							size="sm"
							className="text-xs text-zinc-600 hover:text-zinc-900 h-8 cursor-pointer"
							onClick={() => setSelectedIds(new Set())}
						>
							Clear Selection
						</Button>
						<Button
							variant="destructive"
							size="sm"
							className="gap-1.5 text-xs h-8 px-3 bg-red-600 hover:bg-red-700 text-white shadow-none cursor-pointer"
							onClick={() => setIsBulkDeleteModalOpen(true)}
						>
							<RiDeleteBinLine className="size-3.5" />
							<span>Delete Selected ({selectedIds.size})</span>
						</Button>
					</div>
				</div>
			)}

			{/* Table */}
			<div className="border border-gray-200 rounded-lg bg-white overflow-x-auto shadow-none">
				<Table className="[&_tr]:border-gray-100">
					<TableHeader className="bg-gray-50/50">
						<TableRow className="bg-gray-50/50 hover:bg-gray-50/50">
							<TableHead className="w-10 px-3">
								<div className="flex items-center justify-center">
									<Checkbox
										checked={isAllCurrentPageSelected}
										onCheckedChange={handleSelectAllCurrentPage}
										aria-label="Select all rows on current page"
									/>
								</div>
							</TableHead>
							<SortableTableHead
								sortKey="title"
								currentSortKey={sortKey}
								sortOrder={sortOrder}
								onSort={handleSort}
								className="w-62.5 font-medium text-gray-700"
							>
								Knowledge Title
							</SortableTableHead>
							<TableHead className="w-37.5 font-medium text-gray-700">Category</TableHead>
							<TableHead className="w-36 font-medium text-gray-700">Uploaded By</TableHead>
							<SortableTableHead
								sortKey="created_at"
								currentSortKey={sortKey}
								sortOrder={sortOrder}
								onSort={handleSort}
								className="w-40 font-medium text-gray-700"
							>
								Date
							</SortableTableHead>
							<TableHead className="font-medium text-gray-700">Description</TableHead>
							<SortableTableHead
								sortKey="status"
								currentSortKey={sortKey}
								sortOrder={sortOrder}
								onSort={handleSort}
								className="w-30 font-medium text-gray-700"
							>
								Status
							</SortableTableHead>
							<TableHead className="w-30 font-medium text-gray-700 text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{isLoading && (
							<TableRow>
								<TableCell colSpan={8} className="text-center py-8 text-zinc-600">
									<div className="flex items-center justify-center">
										<RiLoader4Line className="w-5 h-5 animate-spin mr-2" />
										Loading knowledge base...
									</div>
								</TableCell>
							</TableRow>
						)}

						{isError && (
							<TableRow>
								<TableCell colSpan={8} className="text-center py-8 text-red-600">
									Failed to load knowledge base documents.
								</TableCell>
							</TableRow>
						)}

						{!isLoading && !isError && filteredList?.length === 0 && (
							<TableRow>
								<TableCell colSpan={8} className="text-center py-12 text-zinc-600">
									<div className="flex flex-col items-center justify-center gap-2">
										<p className="text-sm">No knowledge base documents matching your filters.</p>
										{hasActiveFilters && (
											<Button
												type="button"
												variant="outline"
												size="sm"
												onClick={handleResetFilters}
												className="mt-1 text-xs cursor-pointer"
											>
												Clear all filters
											</Button>
										)}
									</div>
								</TableCell>
							</TableRow>
						)}

						{!isLoading &&
							paginatedItems?.map((row) => (
								<TableRow
									key={row.isBatch ? `batch-${row.batchId}` : `doc-${row.id}`}
									className="hover:bg-gray-50/60 cursor-pointer"
									onClick={() => handleRowClick(row)}
								>
									<TableCell className="w-10 px-3" onClick={(e) => e.stopPropagation()}>
										<div className="flex items-center justify-center">
											<Checkbox
												checked={
													row.allDocIds && row.allDocIds.length > 0
														? row.allDocIds.every((id) => selectedIds.has(id))
														: selectedIds.has(row.id)
												}
												onCheckedChange={() => {
													const targetIds =
														row.allDocIds && row.allDocIds.length > 0
															? row.allDocIds
															: [row.id];
													setSelectedIds((prev) => {
														const next = new Set(prev);
														const hasAll = targetIds.every((id) => next.has(id));
														if (hasAll) {
															targetIds.forEach((id) => next.delete(id));
														} else {
															targetIds.forEach((id) => next.add(id));
														}
														return next;
													});
												}}
												aria-label={`Select row ${row.title}`}
											/>
										</div>
									</TableCell>
									<TableCell>
										<div className="flex items-center gap-2 min-w-0 max-w-50 sm:max-w-62.5">
											{row.isBatch && row.documentCount && row.documentCount > 1 ? (
												<RiBookletLine className="size-4 shrink-0 text-gray-600" />
											) : (
												<RiBookOpenLine className="size-4 shrink-0 text-gray-600" />
											)}
											<span
												className="font-medium text-gray-900 truncate"
												title={row.title || undefined}
											>
												{row.title}
											</span>
											{row.isBatch && row.documentCount && row.documentCount > 1 && (
												<Badge
													variant="secondary"
													className="bg-blue-50 text-blue-700 border-blue-200 text-[10px] px-1.5 py-0 shrink-0 font-normal rounded-md"
												>
													{row.documentCount} files
												</Badge>
											)}
										</div>
									</TableCell>
									<TableCell>
										<div className="flex flex-wrap items-center gap-1">
											{row.categories.length > 0 ? (
												<>
													{row.categories.slice(0, 2).map((cat, idx) => (
														<Badge
															key={idx}
															variant="secondary"
															className="bg-gray-100 text-gray-700 hover:bg-gray-100 rounded-md"
														>
															{cat}
														</Badge>
													))}
													{row.categories.length > 2 && (
														<Badge
															variant="secondary"
															className="bg-gray-100 text-zinc-700 hover:bg-gray-200 text-[11px] px-1.5 py-0 rounded-md cursor-default font-medium"
															title={row.categories.slice(2).join(", ")}
														>
															+{row.categories.length - 2}
														</Badge>
													)}
												</>
											) : (
												<span className="text-xs text-zinc-600">-</span>
											)}
										</div>
									</TableCell>
									<TableCell>
										<div className="flex items-center gap-2">
											<div className="size-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-[11px] font-semibold shrink-0">
												{(row.uploadedByName || "A").charAt(0).toUpperCase()}
											</div>
											<span
												className="text-xs font-medium text-zinc-700 truncate max-w-28"
												title={row.uploadedByName || "Admin"}
											>
												{row.uploadedByName || "Admin"}
											</span>
										</div>
									</TableCell>
									<TableCell className="whitespace-nowrap text-sm text-zinc-600">
										<div className="flex flex-col gap-0.5">
											<span className="text-xs text-zinc-900 font-medium">
												{row.created_at
													? `${new Date(row.created_at).toLocaleDateString("en-GB", {
															day: "2-digit",
															month: "short",
															year: "numeric",
													  })} ${new Date(row.created_at).toLocaleTimeString("en-GB", {
															hour: "2-digit",
															minute: "2-digit",
													  })}`
													: "-"}
											</span>
											{row.status === "APPROVED" && (row.approved_at || row.rawItem.approved_at) && (
												<span
													className="text-[10px] text-emerald-700 flex items-center gap-1"
													title={`Approved on ${new Date(row.approved_at || row.rawItem.approved_at!).toLocaleString("id-ID")}`}
												>
													<RiCheckLine className="size-3 shrink-0" />
													<span>
														Appr:{" "}
														{new Date(row.approved_at || row.rawItem.approved_at!).toLocaleDateString("en-GB", {
															day: "2-digit",
															month: "short",
														})}{" "}
														{new Date(row.approved_at || row.rawItem.approved_at!).toLocaleTimeString("en-GB", {
															hour: "2-digit",
															minute: "2-digit",
														})}
													</span>
												</span>
											)}
										</div>
									</TableCell>
									<TableCell className="max-w-xl">
										<p className="text-sm text-gray-600 truncate">
											{row.description}
										</p>
									</TableCell>
									<TableCell>{getStatusBadge(row.status)}</TableCell>
									<TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
										<div className="flex justify-end items-center">
											<DropdownMenu>
												<DropdownMenuTrigger
													render={
														<Button
															variant="ghost"
															size="icon"
															className="size-8 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100"
														>
															<RiMore2Line className="size-4" />
														</Button>
													}
												/>
												<DropdownMenuContent align="end" className="w-40 bg-white border-gray-200">
													<DropdownMenuItem
														onClick={() => handleRowClick(row)}
														className="text-xs text-gray-700 cursor-pointer"
													>
														<RiEyeLine className="size-3.5 mr-2" />
														<span>View Details</span>
													</DropdownMenuItem>
													<DropdownMenuItem
														onClick={() => {
															if (row.isBatch && row.batchId) {
																router.push(`${basePath}/batch/${row.batchId}?edit=true`);
															} else {
																router.push(`${basePath}/${row.id}?edit=true`);
															}
														}}
														className="text-xs text-gray-700 cursor-pointer"
													>
														<RiEdit2Line className="size-3.5 mr-2" />
														<span>Edit Knowledge</span>
													</DropdownMenuItem>
													<DropdownMenuItem
														onClick={() => {
															setAttachKnowledgeId(row.id);
															setAttachKnowledgeIds(row.allDocIds || [row.id]);
															setAttachKnowledgeTitle(row.title);
															setAttachCurrentProjectId(
																row.projectId || row.rawItem?.project_id || null,
															);
															setIsAttachModalOpen(true);
														}}
														className="text-xs text-gray-700 cursor-pointer"
													>
														<RiBookOpenLine className="size-3.5 mr-2" />
														<span>Attach to Project</span>
													</DropdownMenuItem>
													<DropdownMenuItem
														onClick={(e) => handleDeleteClick(row, e)}
														className="text-xs text-red-600 hover:text-red-700 hover:bg-red-50 cursor-pointer"
													>
														<RiDeleteBinLine className="size-3.5 mr-2" />
														<span>Delete</span>
													</DropdownMenuItem>
												</DropdownMenuContent>
											</DropdownMenu>
										</div>
									</TableCell>
								</TableRow>
							))}
					</TableBody>
				</Table>
			</div>

			<DataTablePagination
				page={page}
				pageSize={pageSize}
				totalPages={totalPages}
				totalItems={totalItems}
				startIndex={startIndex}
				endIndex={endIndex}
				onPageChange={setPage}
				onPageSizeChange={setPageSize}
				itemName="documents"
			/>

			<AttachProjectDialog
				isOpen={isAttachModalOpen}
				onClose={() => setIsAttachModalOpen(false)}
				knowledgeId={attachKnowledgeId}
				knowledgeIds={attachKnowledgeIds}
				knowledgeTitle={attachKnowledgeTitle}
				currentProjectId={attachCurrentProjectId}
			/>

			<ConfirmationModal
				isOpen={deleteModalOpen}
				onOpenChange={setDeleteModalOpen}
				title="Delete Knowledge"
				description={`Are you sure you want to delete "${itemToDelete?.title}"? This action cannot be undone.`}
				confirmText="Delete Knowledge"
				cancelText="Cancel"
				variant="destructive"
				isLoading={deleteMutation.isPending}
				onConfirm={handleConfirmDelete}
			/>

			<ConfirmationModal
				isOpen={isBulkDeleteModalOpen}
				onOpenChange={setIsBulkDeleteModalOpen}
				title={`Delete ${selectedIds.size} Documents?`}
				description={`Are you sure you want to delete ${selectedIds.size} selected document(s)? All vector embeddings, chunks, and uploaded files will be permanently removed.`}
				confirmText={`Delete ${selectedIds.size} Documents`}
				cancelText="Cancel"
				variant="destructive"
				isLoading={isBulkDeleting}
				onConfirm={handleConfirmBulkDelete}
			/>
		</div>
	);
}
