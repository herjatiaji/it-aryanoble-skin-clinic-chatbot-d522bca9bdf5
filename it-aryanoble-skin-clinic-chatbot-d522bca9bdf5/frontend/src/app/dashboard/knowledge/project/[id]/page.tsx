"use client";

import { useCategories } from "@/app/dashboard/category/hooks/use-categories";
import {
	extractKnowledgeCategories,
	type KnowledgeResponse,
} from "@/app/dashboard/knowledge/api/types";
import { AttachProjectDialog } from "@/app/dashboard/knowledge/components/attach-project-dialog";
import { ProjectDialog } from "@/app/dashboard/knowledge/components/project-dialog";
import { useDeleteKnowledge } from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { useDeleteProject, useProjectDetail } from "@/app/dashboard/knowledge/hooks/use-projects";
import { stripMarkdown } from "@/lib/utils";
import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { DataTablePagination } from "@/components/shared/data-table-pagination";
import { SearchBar } from "@/components/shared/search-bar";
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
import { useDebounce } from "@/hooks/use-debounce";
import { usePagination } from "@/hooks/use-pagination";
import { useSafeBack } from "@/hooks/use-safe-back";
import { useTableSort } from "@/hooks/use-table-sort";
import {
	RiAddCircleLine,
	RiArrowDownSLine,
	RiArrowLeftLine,
	RiBookOpenLine,
	RiBookletLine,
	RiCheckLine,
	RiCloseLine,
	RiDatabase2Line,
	RiDeleteBin7Line,
	RiDeleteBinLine,
	RiEdit2Line,
	RiEyeLine,
	RiFilterOffLine,
	RiLoader4Line,
	RiMoneyDollarCircleLine,
	RiMore2Line,
	RiRobot2Line,
	RiSearchLine,
} from "@remixicon/react";
import { useRouter } from "next/navigation";
import { use, useMemo, useState } from "react";
import { toast } from "sonner";

interface DisplayRowItem {
	id: string;
	isBatch: boolean;
	batchId?: string;
	title: string;
	status: string;
	created_at?: string;
	description: string;
	documentCount?: number;
	rawItem: KnowledgeResponse;
	allFileNames: string[];
	categories: string[];
	allDocIds?: string[];
}

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
	const router = useRouter();
	const handleBack = useSafeBack("/dashboard/knowledge");
	const unwrappedParams = use(params);
	const projectId = unwrappedParams.id;

	const { data: project, isLoading, isError } = useProjectDetail(projectId);
	const { data: availableCategories = [] } = useCategories();
	const deleteProjectMutation = useDeleteProject();
	const deleteKnowledgeMutation = useDeleteKnowledge();

	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 300);
	const [statusFilter, setStatusFilter] = useState("ALL");
	const [categoryFilter, setCategoryFilter] = useState("ALL");
	const [isCategoryPopoverOpen, setIsCategoryPopoverOpen] = useState(false);
	const [categorySearchQuery, setCategorySearchQuery] = useState("");
	const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);

	const filteredAvailableCategories = useMemo(() => {
		if (!categorySearchQuery.trim()) return availableCategories;
		const q = categorySearchQuery.toLowerCase().trim();
		return availableCategories.filter((c) => c.name.toLowerCase().includes(q));
	}, [availableCategories, categorySearchQuery]);

	// Delete Modals State
	const [deleteProjectModalOpen, setDeleteProjectModalOpen] = useState(false);
	const [deleteKnowledgeModalOpen, setDeleteKnowledgeModalOpen] = useState(false);
	const [knowledgeToDelete, setKnowledgeToDelete] = useState<DisplayRowItem | null>(null);

	// Attach Project Modal State
	const [isAttachModalOpen, setIsAttachModalOpen] = useState(false);
	const [attachKnowledgeId, setAttachKnowledgeId] = useState<string | null>(null);
	const [attachKnowledgeIds, setAttachKnowledgeIds] = useState<string[] | undefined>(undefined);
	const [attachKnowledgeTitle, setAttachKnowledgeTitle] = useState("");
	const [attachCurrentProjectId, setAttachCurrentProjectId] = useState<string | null>(null);

	const handleConfirmDeleteProject = async () => {
		if (!project) return;
		await deleteProjectMutation.mutateAsync(project.id);
		setDeleteProjectModalOpen(false);
		router.push("/dashboard/knowledge");
	};

	const handleDeleteKnowledgeClick = (row: DisplayRowItem, e: React.MouseEvent) => {
		e.stopPropagation();
		setKnowledgeToDelete(row);
		setDeleteKnowledgeModalOpen(true);
	};

	const handleConfirmDeleteKnowledge = async () => {
		if (knowledgeToDelete) {
			const idsToDelete =
				knowledgeToDelete.allDocIds && knowledgeToDelete.allDocIds.length > 0
					? knowledgeToDelete.allDocIds
					: [knowledgeToDelete.id];

			try {
				if (idsToDelete.length > 1) {
					await Promise.all(
						idsToDelete.map((id) => deleteKnowledgeMutation.mutateAsync({ id, hideToast: true })),
					);
					toast.success(`All ${idsToDelete.length} documents deleted successfully!`);
				} else {
					await deleteKnowledgeMutation.mutateAsync(idsToDelete[0]);
				}
			} catch {
				// handled by mutation
			}
			setDeleteKnowledgeModalOpen(false);
			setKnowledgeToDelete(null);
		}
	};

	const handleRowClick = (row: DisplayRowItem) => {
		if (row.isBatch && row.batchId) {
			router.push(`/dashboard/knowledge/batch/${row.batchId}`);
		} else {
			router.push(`/dashboard/knowledge/${row.id}`);
		}
	};

	// Group knowledges by batch_id if present (exact same grouping logic as main knowledge base)
	const displayRows = useMemo<DisplayRowItem[]>(() => {
		if (!project?.knowledges) return [];

		const batchMap = new Map<string, KnowledgeResponse[]>();
		const singleItems: KnowledgeResponse[] = [];

		for (const item of project.knowledges) {
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
					description: stripMarkdown(doc.ai_summary || doc.content) || "No description available.",
					documentCount: 1,
					rawItem: doc,
					allFileNames: [doc.file_name],
					categories: combinedCategories,
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

				rows.push({
					id: docs[0].id,
					isBatch: true,
					batchId,
					title: displayTitle,
					status: aggStatus,
					created_at: mostRecentDate,
					description: stripMarkdown(batchSummary) || `Batch upload containing ${docs.length} documents.`,
					documentCount: docs.length,
					rawItem: docs[0],
					allFileNames: allNames,
					categories: combinedCategories,
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
				description: stripMarkdown(doc.ai_summary || doc.content) || "No description available.",
				documentCount: 1,
				rawItem: doc,
				allFileNames: [doc.file_name],
				categories: extractKnowledgeCategories(doc),
				allDocIds: [doc.id],
			});
		}

		return rows;
	}, [project]);

	const isCategoryMatch = (itemCategories: string[], filterCat: string) => {
		if (!filterCat || filterCat === "ALL") return true;
		const target = filterCat.toLowerCase();
		return itemCategories.some(
			(c) => c.toLowerCase() === target || c.toLowerCase().includes(target),
		);
	};

	const { sortKey, sortOrder, handleSort, sortItems } = useTableSort({
		initialSortKey: "created_at",
		initialSortOrder: "desc",
	});

	const filteredList = useMemo(() => {
		const result = (displayRows || [])
			.filter((item) => (statusFilter !== "ALL" ? item.status === statusFilter : true))
			.filter((item) => isCategoryMatch(item.categories, categoryFilter))
			.filter(
				(item) =>
					item.title.toLowerCase().includes(debouncedSearch.toLowerCase()) ||
					item.allFileNames.some((f) => f.toLowerCase().includes(debouncedSearch.toLowerCase())) ||
					item.description.toLowerCase().includes(debouncedSearch.toLowerCase()) ||
					item.categories.some((c) => c.toLowerCase().includes(debouncedSearch.toLowerCase())),
			);

		return sortItems<DisplayRowItem>(result);
	}, [displayRows, statusFilter, categoryFilter, debouncedSearch, sortItems]);

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

	const hasActiveFilters =
		searchQuery.trim() !== "" || statusFilter !== "ALL" || categoryFilter !== "ALL";

	const handleResetFilters = () => {
		setSearchQuery("");
		setStatusFilter("ALL");
		setCategoryFilter("ALL");
		setPage(1);
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

	if (isLoading) {
		return (
			<div className="flex flex-col items-center justify-center h-full p-12 text-zinc-600">
				<RiLoader4Line className="w-6 h-6 animate-spin text-blue-600 mb-2" />
				<span className="text-sm">Loading project...</span>
			</div>
		);
	}

	if (isError || !project) {
		return (
			<div className="flex flex-col items-center justify-center h-full p-12 text-zinc-600">
				<p className="text-sm text-red-600 mb-4">Project not found or failed to load.</p>
				<Button variant="outline" size="sm" onClick={handleBack}>
					<RiArrowLeftLine className="w-4 h-4 mr-1.5" />
					Back to Knowledge Base
				</Button>
			</div>
		);
	}

	return (
		<div className="flex flex-col h-full bg-white">
			{/* Header matching Knowledge Detail with Edit & Delete buttons on right */}
			<div className="flex items-center gap-4 px-4 py-3 border-b border-gray-200 shrink-0 bg-white justify-between">
				<div className="flex items-center gap-3 min-w-0">
					<Button
						variant="ghost"
						size="icon"
						onClick={handleBack}
						className="size-9 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 shrink-0"
						title="Back"
						aria-label="Back"
					>
						<RiArrowLeftLine className="size-5" />
					</Button>
					<div className="min-w-0">
						<h1 className="text-base font-semibold text-gray-900 truncate">{project.name}</h1>
					</div>
				</div>

				<div className="flex items-center gap-2">
					<Button
						onClick={() => setDeleteProjectModalOpen(true)}
						disabled={deleteProjectMutation.isPending}
						variant="outline"
						className="gap-2 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50 hover:border-red-300 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
					>
						<RiDeleteBin7Line className="size-4" />
						Delete Project
					</Button>

					<Button
						variant="outline"
						className="gap-2 border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						onClick={() => setIsEditDialogOpen(true)}
					>
						<RiEdit2Line className="size-4" />
						Edit Project
					</Button>

					<Button
						className="gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						onClick={() => router.push(`/dashboard/ingest?projectId=${project.id}`)}
					>
						<RiAddCircleLine className="size-4" />
						Add Knowledge
					</Button>
				</div>
			</div>

			{/* Main Page Body matching Knowledge Base layout */}
			<div className="flex flex-col h-full gap-6 p-6 overflow-y-auto">
				{/* Summary displaying Total Knowledge */}
				<div className="w-full">
					<p className="text-sm text-zinc-600 mb-3">Here is the overview data of the ingestion</p>
					<div className="inline-flex border border-gray-200 rounded-md bg-white overflow-hidden shadow-none">
						<div className="w-64 flex items-center gap-4 p-4">
							<div className="p-3 rounded-md bg-blue-50">
								<RiRobot2Line className="w-6 h-6 text-blue-600" />
							</div>
							<div>
								<p className="text-sm text-zinc-600">Total Knowledge</p>
								<p className="text-2xl font-medium text-gray-900 mt-1">
									{project.knowledges?.length ?? 0}
								</p>
							</div>
						</div>
					</div>
				</div>

				{/* Main Knowledge Base Table Content within Project */}
				<div className="flex flex-col gap-4">
					<div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
						<div>
							<h2 className="text-base font-semibold text-gray-900">Knowledge List</h2>
							<p className="text-xs text-gray-500 mt-0.5">
								Documents and knowledge files categorized under this project.
							</p>
						</div>

						{/* Search & Filters Bar */}
						<div className="flex flex-wrap items-center gap-3">
							<SearchBar
								containerClassName="w-72"
								placeholder="Search documents..."
								value={searchQuery}
								onChange={(e) => setSearchQuery(e.target.value)}
							/>

							<div className="flex items-center gap-2">
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
												className="min-w-44 justify-between gap-2 bg-white font-normal text-gray-700 hover:bg-gray-50 border-gray-200 shadow-none cursor-pointer rounded-lg text-sm h-10"
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
															isSelected
																? "bg-blue-50 text-blue-700"
																: "text-zinc-700 hover:bg-zinc-100"
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
												className="min-w-36 justify-start gap-2 bg-white font-normal text-gray-700 hover:bg-gray-50 border-gray-200 shadow-none cursor-pointer"
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
					</div>

					{/* Table */}
					<div className="border border-gray-200 rounded-lg bg-white overflow-hidden shadow-none">
						<Table className="[&_tr]:border-gray-100">
							<TableHeader className="bg-gray-50/50">
								<TableRow className="bg-gray-50/50 hover:bg-gray-50/50">
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
									<SortableTableHead
										sortKey="created_at"
										currentSortKey={sortKey}
										sortOrder={sortOrder}
										onSort={handleSort}
										className="w-35 font-medium text-gray-700"
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
									<TableHead className="w-30 font-medium text-gray-700 text-right">
										Actions
									</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{filteredList?.length === 0 ? (
									<TableRow>
										<TableCell colSpan={6} className="text-center py-12 text-zinc-600">
											<div className="flex flex-col items-center justify-center gap-2">
												<p className="text-sm">
													{hasActiveFilters
														? "No knowledge base documents matching your filters."
														: "No knowledge base documents in this project."}
												</p>
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
								) : (
									!isLoading &&
									paginatedItems?.map((row) => (
										<TableRow
											key={row.isBatch ? `batch-${row.batchId}` : `doc-${row.id}`}
											className="hover:bg-gray-50/60 cursor-pointer"
											onClick={() => handleRowClick(row)}
										>
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

											<TableCell className="whitespace-nowrap text-sm text-zinc-600">
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
																	className="size-8 text-gray-500 hover:text-gray-900"
																>
																	<RiMore2Line className="size-4" />
																</Button>
															}
														/>
														<DropdownMenuContent
															align="end"
															className="w-40 bg-white border-gray-200"
														>
															<DropdownMenuItem
																onClick={() => handleRowClick(row)}
																className="text-xs text-gray-700 cursor-pointer"
															>
																<RiEyeLine className="size-3.5 mr-2" />
																<span>View Details</span>
															</DropdownMenuItem>
															<DropdownMenuItem
																onClick={() => {
																	setAttachKnowledgeId(row.id);
																	setAttachKnowledgeIds(row.allDocIds || [row.id]);
																	setAttachKnowledgeTitle(row.title);
																	setAttachCurrentProjectId(projectId);
																	setIsAttachModalOpen(true);
																}}
																className="text-xs text-gray-700 cursor-pointer"
															>
																<RiBookOpenLine className="size-3.5 mr-2" />
																<span>Attach to Project</span>
															</DropdownMenuItem>
															<DropdownMenuItem
																onClick={(e) => handleDeleteKnowledgeClick(row, e)}
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
									))
								)}
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
				</div>
			</div>

			<ProjectDialog
				isOpen={isEditDialogOpen}
				onClose={() => setIsEditDialogOpen(false)}
				projectToEdit={project}
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
				isOpen={deleteKnowledgeModalOpen}
				onOpenChange={setDeleteKnowledgeModalOpen}
				title="Delete Knowledge"
				description={`Are you sure you want to delete "${knowledgeToDelete?.title}"? This action cannot be undone.`}
				confirmText="Delete Knowledge"
				cancelText="Cancel"
				variant="destructive"
				isLoading={deleteKnowledgeMutation.isPending}
				onConfirm={handleConfirmDeleteKnowledge}
			/>

			<ConfirmationModal
				isOpen={deleteProjectModalOpen}
				onOpenChange={setDeleteProjectModalOpen}
				title="Delete Project"
				description={`Are you sure you want to delete project "${project?.name}"? All knowledge records will remain in the database.`}
				confirmText="Delete Project"
				cancelText="Cancel"
				variant="destructive"
				isLoading={deleteProjectMutation.isPending}
				onConfirm={handleConfirmDeleteProject}
			/>
		</div>
	);
}
