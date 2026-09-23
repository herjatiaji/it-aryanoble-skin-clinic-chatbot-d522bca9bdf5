"use client";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
	RiCloseLine,
	RiCornerDownLeftLine,
	RiFolderLine,
	RiHospitalLine,
	RiLoader4Line,
	RiSearchLine,
	RiSparklingLine,
	RiUser3Line,
} from "@remixicon/react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
	CategorySearchResult,
	ChatSearchResult,
	KnowledgeSearchResult,
	ProjectSearchResult,
} from "./api";
import { useGlobalSearch } from "./hooks/use-global-search";

type SearchCategory = "all" | "projects" | "knowledge" | "chats" | "categories";

type FlatSearchItem =
	| { type: "project"; data: ProjectSearchResult }
	| { type: "knowledge"; data: KnowledgeSearchResult }
	| { type: "chat"; data: ChatSearchResult }
	| { type: "category"; data: CategorySearchResult };

function HighlightSnippet({ text, query }: { text?: string | null; query: string }) {
	if (!text) return null;
	if (!query.trim()) return <span>{text}</span>;

	const words = query
		.trim()
		.split(/\s+/)
		.filter((w) => w.length > 0);

	if (words.length === 0) return <span>{text}</span>;

	const escapedWords = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
	const splitRegex = new RegExp(`(${escapedWords.join("|")})`, "gi");
	const parts = text.split(splitRegex);
	const lowerWords = words.map((w) => w.toLowerCase());

	return (
		<span>
			{parts.map((part, i) =>
				lowerWords.includes(part.toLowerCase()) ? (
					<span key={i} className="font-semibold text-blue-600 bg-blue-50/90 px-0.5 rounded-xs">
						{part}
					</span>
				) : (
					<React.Fragment key={i}>{part}</React.Fragment>
				),
			)}
		</span>
	);
}

export function GlobalSearchBar({ className }: { className?: string }) {
	const router = useRouter();
	const [isOpen, setIsOpen] = useState(false);
	const [searchQuery, setSearchQuery] = useState("");
	const [activeTab, setActiveTab] = useState<SearchCategory>("all");
	const [selectedIndex, setSelectedIndex] = useState(0);

	const containerRef = useRef<HTMLDivElement>(null);
	const inputRef = useRef<HTMLInputElement>(null);
	const listContainerRef = useRef<HTMLDivElement>(null);

	// Always query all categories so tab badges consistently display accurate hit counts
	const { data, isLoading, isDebouncing } = useGlobalSearch(searchQuery, "all");

	const isSearching = isLoading || isDebouncing;
	const projectResults = useMemo(() => data?.projects ?? [], [data?.projects]);
	const knowledgeResults = useMemo(() => data?.knowledge ?? [], [data?.knowledge]);
	const chatResults = useMemo(() => data?.chats ?? [], [data?.chats]);
	const categoryResults = useMemo(() => data?.categories ?? [], [data?.categories]);

	const totalResults =
		projectResults.length +
		knowledgeResults.length +
		chatResults.length +
		categoryResults.length;

	// Flatten results in exact requested order: Project -> Knowledge -> Chat History -> Category
	const flatItems: FlatSearchItem[] = useMemo(() => {
		const items: FlatSearchItem[] = [];
		if (activeTab === "all" || activeTab === "projects") {
			projectResults.forEach((p) => items.push({ type: "project", data: p }));
		}
		if (activeTab === "all" || activeTab === "knowledge") {
			knowledgeResults.forEach((k) => items.push({ type: "knowledge", data: k }));
		}
		if (activeTab === "all" || activeTab === "chats") {
			chatResults.forEach((c) => items.push({ type: "chat", data: c }));
		}
		if (activeTab === "all" || activeTab === "categories") {
			categoryResults.forEach((cat) => items.push({ type: "category", data: cat }));
		}
		return items;
	}, [projectResults, knowledgeResults, chatResults, categoryResults, activeTab]);

	// Global shortcut Cmd+K / Ctrl+K
	useEffect(() => {
		const handleKeyDown = (e: KeyboardEvent) => {
			if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
				e.preventDefault();
				inputRef.current?.focus();
				setIsOpen(true);
			}
		};

		window.addEventListener("keydown", handleKeyDown);
		return () => window.removeEventListener("keydown", handleKeyDown);
	}, []);

	// Click outside listener
	useEffect(() => {
		const handleClickOutside = (e: MouseEvent) => {
			if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
				setIsOpen(false);
			}
		};

		document.addEventListener("mousedown", handleClickOutside);
		return () => document.removeEventListener("mousedown", handleClickOutside);
	}, []);

	// Reset selected index
	useEffect(() => {
		const timer = setTimeout(() => {
			setSelectedIndex(0);
		}, 0);
		return () => clearTimeout(timer);
	}, [flatItems.length, activeTab]);

	// Auto-scroll selected item into view on keyboard navigation (isolated strictly to dropdown list)
	useEffect(() => {
		if (!isOpen) return;
		const timer = setTimeout(() => {
			const container = listContainerRef.current;
			const selectedEl = container?.querySelector<HTMLElement>(`[data-selected="true"]`);
			if (container && selectedEl) {
				const containerRect = container.getBoundingClientRect();
				const elemRect = selectedEl.getBoundingClientRect();

				if (elemRect.top < containerRect.top) {
					container.scrollTop -= containerRect.top - elemRect.top;
				} else if (elemRect.bottom > containerRect.bottom) {
					container.scrollTop += elemRect.bottom - containerRect.bottom;
				}
			}
		}, 0);
		return () => clearTimeout(timer);
	}, [selectedIndex, isOpen]);

	const handleSelectItem = (item: FlatSearchItem) => {
		setIsOpen(false);
		inputRef.current?.blur();
		if (item.type === "project") {
			router.push(`/dashboard/knowledge/project/${item.data.id}`);
		} else if (item.type === "knowledge") {
			router.push(`/dashboard/knowledge/${item.data.id}`);
		} else if (item.type === "chat") {
			router.push(`/dashboard/chat-history/${item.data.id}`);
		} else if (item.type === "category") {
			router.push(`/dashboard/category?search=${encodeURIComponent(item.data.name)}`);
		}
	};

	const handleKeyDown = (e: React.KeyboardEvent) => {
		if (e.key === "ArrowDown") {
			e.preventDefault();
			if (!isOpen) {
				setIsOpen(true);
				return;
			}
			setSelectedIndex((prev) => (prev < flatItems.length - 1 ? prev + 1 : 0));
		} else if (e.key === "ArrowUp") {
			e.preventDefault();
			if (!isOpen) {
				setIsOpen(true);
				return;
			}
			setSelectedIndex((prev) => (prev > 0 ? prev - 1 : flatItems.length - 1));
		} else if (e.key === "Enter") {
			if (isOpen && flatItems.length > 0) {
				e.preventDefault();
				const selected = flatItems[selectedIndex];
				if (selected) {
					handleSelectItem(selected);
				}
			}
		} else if (e.key === "Escape") {
			e.preventDefault();
			setIsOpen(false);
			inputRef.current?.blur();
		}
	};

	const hasResults = flatItems.length > 0;
	const showEmptyState = searchQuery.trim().length > 0 && !isSearching && !hasResults;

	return (
		<div ref={containerRef} className={cn("relative w-full max-w-xl lg:max-w-2xl", className)}>
			{/* Dashboard-Styled Search Input */}
			<div className="relative flex items-center w-full">
				<RiSearchLine className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground size-4 pointer-events-none" />

				<Input
					ref={inputRef}
					type="text"
					autoComplete="off"
					spellCheck={false}
					value={searchQuery}
					onFocus={() => setIsOpen(true)}
					onChange={(e) => {
						setSearchQuery(e.target.value);
						if (!isOpen) setIsOpen(true);
					}}
					onKeyDown={handleKeyDown}
					placeholder="Search knowledge, projects, categories, chats..."
					className={cn(
						"pl-9 pr-12 bg-white border-gray-200 focus-visible:ring-1 focus-visible:ring-blue-500 h-9 text-xs sm:text-sm rounded-lg transition-all",
						isOpen && "border-blue-400 ring-1 ring-blue-400/20",
					)}
				/>

				{/* Right icon: Loader when searching, Clear button when text present, or Shortcut badge when empty/unfocused */}
				<div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center">
					{isSearching ? (
						<RiLoader4Line className="size-3.5 animate-spin text-muted-foreground" />
					) : searchQuery ? (
						<button
							type="button"
							onClick={() => {
								setSearchQuery("");
								inputRef.current?.focus();
							}}
							className="text-muted-foreground hover:text-foreground rounded-md hover:bg-gray-100 p-0.5 transition-colors cursor-pointer"
							title="Clear search"
						>
							<RiCloseLine className="size-3.5" />
						</button>
					) : !isOpen ? (
						<kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground shadow-2xs pointer-events-none">
							<span className="text-xs">⌘</span>K
						</kbd>
					) : null}
				</div>
			</div>

			{/* Anchored Dropdown Panel (Exact width matching the searchbar) */}
			{isOpen && (
				<div className="absolute top-full left-0 right-0 mt-1.5 w-full rounded-xl border border-gray-200 bg-white z-50 overflow-hidden shadow-xl animate-in fade-in-0 duration-100">
					{/* Category Tabs Header in exact requested order: Project -> Knowledge -> Chat History -> Category */}
					<div className="flex items-center gap-1.5 border-b border-gray-100 px-3 py-2 bg-gray-50/70 text-xs overflow-x-auto no-scrollbar">
						<button
							type="button"
							onClick={() => setActiveTab("all")}
							className={cn(
								"px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer shrink-0",
								activeTab === "all"
									? "bg-white text-foreground border border-gray-200 font-semibold"
									: "text-muted-foreground hover:text-foreground hover:bg-gray-100/80",
							)}
						>
							All {searchQuery.trim() && totalResults > 0 ? `(${totalResults})` : ""}
						</button>
						<button
							type="button"
							onClick={() => setActiveTab("projects")}
							className={cn(
								"inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer shrink-0",
								activeTab === "projects"
									? "bg-white text-foreground border border-gray-200 font-semibold"
									: "text-muted-foreground hover:text-foreground hover:bg-gray-100/80",
							)}
						>
							<RiFolderLine className="size-3.5 text-muted-foreground" />
							Project
							{searchQuery.trim() && projectResults.length > 0 ? ` (${projectResults.length})` : ""}
						</button>
						<button
							type="button"
							onClick={() => setActiveTab("knowledge")}
							className={cn(
								"inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer shrink-0",
								activeTab === "knowledge"
									? "bg-white text-foreground border border-gray-200 font-semibold"
									: "text-muted-foreground hover:text-foreground hover:bg-gray-100/80",
							)}
						>
							<Image
								src="/icons/database.png"
								alt="Knowledge"
								width={14}
								height={14}
								className="size-3.5 shrink-0 object-contain opacity-75"
							/>
							Knowledge
							{searchQuery.trim() && knowledgeResults.length > 0 ? ` (${knowledgeResults.length})` : ""}
						</button>
						<button
							type="button"
							onClick={() => setActiveTab("chats")}
							className={cn(
								"inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer shrink-0",
								activeTab === "chats"
									? "bg-white text-foreground border border-gray-200 font-semibold"
									: "text-muted-foreground hover:text-foreground hover:bg-gray-100/80",
							)}
						>
							<Image
								src="/icons/history.png"
								alt="Chat"
								width={14}
								height={14}
								className="size-3.5 shrink-0 object-contain opacity-75"
							/>
							Chat History
							{searchQuery.trim() && chatResults.length > 0 ? ` (${chatResults.length})` : ""}
						</button>
						<button
							type="button"
							onClick={() => setActiveTab("categories")}
							className={cn(
								"inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer shrink-0",
								activeTab === "categories"
									? "bg-white text-foreground border border-gray-200 font-semibold"
									: "text-muted-foreground hover:text-foreground hover:bg-gray-100/80",
							)}
						>
							<Image
								src="/icons/boxes.png"
								alt="Category"
								width={14}
								height={14}
								className="size-3.5 shrink-0 object-contain opacity-75"
							/>
							Category
							{searchQuery.trim() && categoryResults.length > 0 ? ` (${categoryResults.length})` : ""}
						</button>
					</div>

					{/* Results Body */}
					<div ref={listContainerRef} className="max-h-110 overflow-y-auto divide-y divide-gray-100 p-1.5">
						{/* 1. Empty Query Prompt */}
						{!searchQuery.trim() && (
							<div className="p-4 text-xs text-muted-foreground text-center">
								Type to search projects, knowledge documents, chat histories, and categories...
							</div>
						)}

						{/* 2. Loading State */}
						{isSearching && !hasResults && (
							<div className="p-3 space-y-2">
								<div className="h-4 bg-gray-100 rounded w-1/3 animate-pulse" />
								<div className="h-3 bg-gray-50 rounded w-3/4 animate-pulse" />
							</div>
						)}

						{/* 3. Empty Search Results */}
						{showEmptyState && (
							<div className="py-8 px-4 text-center">
								<p className="text-xs font-medium text-foreground">
									No results found for &ldquo;{searchQuery}&rdquo;
								</p>
								<p className="text-[11px] text-muted-foreground mt-1">
									Try searching broader terms, checking spelling, or changing category filters.
								</p>
							</div>
						)}

						{/* 4. Projects Group Results (1st in Order) */}
						{(activeTab === "all" || activeTab === "projects") && projectResults.length > 0 && (
							<div className="py-1">
								<div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
									Projects ({projectResults.length})
								</div>
								<div className="mt-0.5 space-y-0.5">
									{projectResults.map((p) => {
										const itemIndex = flatItems.findIndex(
											(item) => item.type === "project" && item.data.id === p.id,
										);
										const isSelected = itemIndex === selectedIndex;

										return (
											<div
												key={p.id}
												data-selected={isSelected ? "true" : undefined}
												onClick={() => handleSelectItem({ type: "project", data: p })}
												onMouseEnter={() => setSelectedIndex(itemIndex)}
												className={cn(
													"group flex items-start gap-2.5 p-2 rounded-lg cursor-pointer transition-colors text-left",
													isSelected
														? "bg-muted/70 text-foreground"
														: "hover:bg-muted/40 text-foreground",
												)}
											>
												<RiFolderLine className="size-4 text-muted-foreground shrink-0 mt-0.5" />

												<div className="flex-1 min-w-0">
													<div className="flex items-center justify-between gap-2">
														<span className="text-xs font-medium truncate">{p.name}</span>
														<span className="text-[10px] text-muted-foreground shrink-0">
															{p.document_count} docs
														</span>
													</div>

													{p.description && (
														<p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-1">
															<HighlightSnippet text={p.description} query={searchQuery} />
														</p>
													)}

													<div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
														<span>Project Folder</span>
													</div>
												</div>
											</div>
										);
									})}
								</div>
							</div>
						)}

						{/* 5. Knowledge Group Results (2nd in Order) */}
						{(activeTab === "all" || activeTab === "knowledge") && knowledgeResults.length > 0 && (
							<div className="py-1">
								<div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
									<Image
										src="/icons/database.png"
										alt=""
										width={12}
										height={12}
										className="size-3 shrink-0 object-contain opacity-75"
									/>
									<span>Knowledge Base ({knowledgeResults.length})</span>
								</div>
								<div className="mt-0.5 space-y-0.5">
									{knowledgeResults.map((k) => {
										const itemIndex = flatItems.findIndex(
											(item) => item.type === "knowledge" && item.data.id === k.id,
										);
										const isSelected = itemIndex === selectedIndex;

										return (
											<div
												key={k.id}
												data-selected={isSelected ? "true" : undefined}
												onClick={() => handleSelectItem({ type: "knowledge", data: k })}
												onMouseEnter={() => setSelectedIndex(itemIndex)}
												className={cn(
													"group flex items-start gap-2.5 p-2 rounded-lg cursor-pointer transition-colors text-left",
													isSelected
														? "bg-muted/70 text-foreground"
														: "hover:bg-muted/40 text-foreground",
												)}
											>
												<Image
													src="/icons/database.png"
													alt="Knowledge"
													width={16}
													height={16}
													className="size-4 shrink-0 object-contain opacity-75 mt-0.5"
												/>

												<div className="flex-1 min-w-0">
													<div className="flex items-center justify-between gap-2">
														<span className="text-xs font-medium truncate">{k.title}</span>
														<span className="text-[9px] font-medium tracking-wide uppercase px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground shrink-0">
															{k.type}
														</span>
													</div>

													{k.snippet && (
														<p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-2">
															<HighlightSnippet text={k.snippet} query={searchQuery} />
														</p>
													)}

													<div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
														{k.match_field === "chunk_content" && (
															<span className="inline-flex items-center gap-1">
																<RiSparklingLine className="size-2.5 text-muted-foreground" />
																Matched in document text
															</span>
														)}
														{k.match_field === "summary" && (
															<span className="inline-flex items-center gap-1">
																<RiSparklingLine className="size-2.5 text-muted-foreground" />
																Matched in summary
															</span>
														)}
														{k.match_field === "project" && (
															<span className="inline-flex items-center gap-1">
																<RiFolderLine className="size-2.5 text-muted-foreground" />
																Matched via project
															</span>
														)}
														{k.match_field === "category" && (
															<span className="inline-flex items-center gap-1">
																<Image
																	src="/icons/boxes.png"
																	alt=""
																	width={10}
																	height={10}
																	className="size-2.5 shrink-0 object-contain opacity-75"
																/>
																Matched via category
															</span>
														)}
														{k.project_name && <span>• {k.project_name}</span>}
														{k.categories.length > 0 && <span>• {k.categories.join(", ")}</span>}
													</div>
												</div>
											</div>
										);
									})}
								</div>
							</div>
						)}

						{/* 6. Chat Group Results (3rd in Order) */}
						{(activeTab === "all" || activeTab === "chats") && chatResults.length > 0 && (
							<div className="py-1">
								<div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
									<Image
										src="/icons/history.png"
										alt=""
										width={12}
										height={12}
										className="size-3 shrink-0 object-contain opacity-75"
									/>
									<span>Chat History ({chatResults.length})</span>
								</div>
								<div className="mt-0.5 space-y-0.5">
									{chatResults.map((c) => {
										const itemIndex = flatItems.findIndex(
											(item) => item.type === "chat" && item.data.id === c.id,
										);
										const isSelected = itemIndex === selectedIndex;

										return (
											<div
												key={c.id}
												data-selected={isSelected ? "true" : undefined}
												onClick={() => handleSelectItem({ type: "chat", data: c })}
												onMouseEnter={() => setSelectedIndex(itemIndex)}
												className={cn(
													"group flex items-start gap-2.5 p-2 rounded-lg cursor-pointer transition-colors text-left",
													isSelected
														? "bg-muted/70 text-foreground"
														: "hover:bg-muted/40 text-foreground",
												)}
											>
												<Image
													src="/icons/history.png"
													alt="Chat"
													width={16}
													height={16}
													className="size-4 shrink-0 object-contain opacity-75 mt-0.5"
												/>

												<div className="flex-1 min-w-0">
													<div className="flex items-center justify-between gap-2">
														<span className="text-xs font-semibold truncate group-hover:text-blue-600 transition-colors">
															{c.title}
														</span>
														<span className="text-[9px] font-medium tracking-wide uppercase px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground shrink-0">
															{c.session_type === "DOCTOR" ? "Doctor" : "Assistant"}
														</span>
													</div>

													{c.snippet && (
														<p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-2">
															{c.match_role && c.match_role !== "SUMMARY" && (
																<span className="font-semibold text-foreground mr-1">
																	{c.match_role.toLowerCase() === "user" ? "User: " : "AI: "}
																</span>
															)}
															<HighlightSnippet text={c.snippet} query={searchQuery} />
														</p>
													)}

													<div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
														<span className="inline-flex items-center gap-1">
															<RiUser3Line className="size-2.5 text-muted-foreground" />
															{c.doctor_name}
														</span>
														{c.branch_name && (
															<span className="inline-flex items-center gap-1">
																<RiHospitalLine className="size-2.5 text-muted-foreground" />
																{c.branch_name}
															</span>
														)}
														<span>• {c.message_count} msgs</span>
													</div>
												</div>
											</div>
										);
									})}
								</div>
							</div>
						)}

						{/* 7. Categories Group Results (4th in Order) */}
						{(activeTab === "all" || activeTab === "categories") && categoryResults.length > 0 && (
							<div className="py-1">
								<div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
									<Image
										src="/icons/boxes.png"
										alt=""
										width={12}
										height={12}
										className="size-3 shrink-0 object-contain opacity-75"
									/>
									<span>Categories ({categoryResults.length})</span>
								</div>
								<div className="mt-0.5 space-y-0.5">
									{categoryResults.map((cat) => {
										const itemIndex = flatItems.findIndex(
											(item) => item.type === "category" && item.data.id === cat.id,
										);
										const isSelected = itemIndex === selectedIndex;

										return (
											<div
												key={cat.id}
												data-selected={isSelected ? "true" : undefined}
												onClick={() => handleSelectItem({ type: "category", data: cat })}
												onMouseEnter={() => setSelectedIndex(itemIndex)}
												className={cn(
													"group flex items-start gap-2.5 p-2 rounded-lg cursor-pointer transition-colors text-left",
													isSelected
														? "bg-muted/70 text-foreground"
														: "hover:bg-muted/40 text-foreground",
												)}
											>
												<Image
													src="/icons/boxes.png"
													alt="Category"
													width={16}
													height={16}
													className="size-4 shrink-0 object-contain opacity-75 mt-0.5"
												/>

												<div className="flex-1 min-w-0">
													<div className="flex items-center justify-between gap-2">
														<span className="text-xs font-medium truncate">{cat.name}</span>
														<span className="text-[10px] text-muted-foreground shrink-0">
															{cat.knowledge_count} entries
														</span>
													</div>

													{cat.description && (
														<p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-1">
															<HighlightSnippet text={cat.description} query={searchQuery} />
														</p>
													)}

													<div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
														<span>Knowledge Category</span>
													</div>
												</div>
											</div>
										);
									})}
								</div>
							</div>
						)}
					</div>

					{/* Footer Controls */}
					<div className="flex items-center justify-between px-3 py-1.5 bg-gray-50/80 border-t border-gray-100 text-[10px] text-muted-foreground">
						<div className="flex items-center gap-2">
							<span>Press ↑ ↓ to navigate</span>
							<span>•</span>
							<span>↵ to select</span>
						</div>
						<div className="flex items-center gap-1 text-muted-foreground">
							<RiCornerDownLeftLine className="size-2.5 text-muted-foreground" />
							<span>Instant Search</span>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
