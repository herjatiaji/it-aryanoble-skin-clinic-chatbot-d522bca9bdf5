"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SearchBar } from "@/components/shared/search-bar";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import {
	DropdownMenu,
	DropdownMenuTrigger,
	DropdownMenuContent,
	DropdownMenuRadioGroup,
	DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import {
	RiDatabase2Line,
	RiDeleteBin7Line,
	RiEyeLine,
	RiLoader4Line,
	RiMoneyDollarCircleLine,
} from "@remixicon/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useKnowledgeBaseList, useDeleteKnowledge } from "../../../app/dashboard/knowledge/hooks/use-knowledge";
import { useSession } from "@/hooks/use-session";

export function KnowledgeTable({ type = "PRODUCT" }: { type?: string }) {
	const router = useRouter();
	const [searchQuery, setSearchQuery] = useState("");
	const [statusFilter, setStatusFilter] = useState("ALL");
	const [categoryFilter, setCategoryFilter] = useState("ALL");
	const { data: knowledgeList, isLoading, isError } = useKnowledgeBaseList();
	const deleteMutation = useDeleteKnowledge();
	const { user } = useSession();
	const hasDeleteAccess = user?.accesses?.includes("knowledge:delete");

	const basePath = "/dashboard/knowledge";

	const filteredList = knowledgeList
		?.filter((item) => (type ? item.type === type : true))
		?.filter((item) => (statusFilter !== "ALL" ? item.status === statusFilter : true))
		// We'll leave categoryFilter as a visual stub for now until dynamic categories are fully wired
		?.filter(
			(item) =>
				item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
				item.file_name.toLowerCase().includes(searchQuery.toLowerCase()),
		)
		.sort((a, b) => {
			const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
			const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
			return timeB - timeA;
		});

	const getStatusBadge = (status: string) => {
		switch (status) {
			case "APPROVED":
				return (
					<Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-50">
						{status}
					</Badge>
				);
			case "PENDING":
				return (
					<Badge className="bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-50">
						{status}
					</Badge>
				);
			case "PROCESSING":
				return (
					<Badge className="bg-blue-50 text-blue-700 border-blue-200 animate-pulse hover:bg-blue-50">
						{status}
					</Badge>
				);
			case "REJECTED":
				return (
					<Badge className="bg-red-50 text-red-700 border-red-200 hover:bg-red-50">{status}</Badge>
				);
			default:
				return <Badge variant="secondary">{status}</Badge>;
		}
	};

	return (
		<div className="w-full mt-6">
			{/* Filters */}
			<div className="flex items-center justify-between mb-4">
				<SearchBar
					containerClassName="max-w-md"
					value={searchQuery}
					onChange={(e) => setSearchQuery(e.target.value)}
					placeholder="Search for knowledge title or filename..."
				/>
				<div className="flex items-center gap-3">
					<DropdownMenu>
						<DropdownMenuTrigger
							render={
								<Button
									variant="outline"
									className="w-50 justify-start gap-2 bg-white font-normal text-gray-700 hover:bg-gray-50 border-gray-200"
								/>
							}
						>
							<RiDatabase2Line className="size-4 shrink-0 text-gray-500" />
							<span className="truncate">
								{categoryFilter === "ALL" ? "Filter by category" : categoryFilter}
							</span>
						</DropdownMenuTrigger>
						<DropdownMenuContent className="w-50">
							<DropdownMenuRadioGroup value={categoryFilter} onValueChange={setCategoryFilter}>
								<DropdownMenuRadioItem closeOnClick value="ALL">
									All Categories
								</DropdownMenuRadioItem>
								<DropdownMenuRadioItem closeOnClick value="Acne" disabled>
									Acne (Coming Soon)
								</DropdownMenuRadioItem>
								<DropdownMenuRadioItem closeOnClick value="Skin Whitening" disabled>
									Skin Whitening (Coming Soon)
								</DropdownMenuRadioItem>
							</DropdownMenuRadioGroup>
						</DropdownMenuContent>
					</DropdownMenu>

					<DropdownMenu>
						<DropdownMenuTrigger
							render={
								<Button
									variant="outline"
									className="w-45 justify-start gap-2 bg-white font-normal text-gray-700 hover:bg-gray-50 border-gray-200"
								/>
							}
						>
							<RiMoneyDollarCircleLine className="size-4 shrink-0 text-gray-500" />
							<span className="truncate">
								{statusFilter === "ALL"
									? "Filter by status"
									: statusFilter.charAt(0) + statusFilter.slice(1).toLowerCase()}
							</span>
						</DropdownMenuTrigger>
						<DropdownMenuContent className="w-45">
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
								<DropdownMenuRadioItem closeOnClick value="REJECTED">
									Rejected
								</DropdownMenuRadioItem>
							</DropdownMenuRadioGroup>
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
			</div>

			{/* Table */}
			<div className="border border-gray-100 rounded-md bg-white overflow-hidden">
				<Table className="[&_tr]:border-gray-100">
					<TableHeader className="bg-gray-50/50">
						<TableRow className="bg-gray-50/50 hover:bg-gray-50/50">
							<TableHead className="w-62.5 font-medium text-gray-700">Knowledge Title</TableHead>
							<TableHead className="w-37.5 font-medium text-gray-700">Category</TableHead>
							<TableHead className="font-medium text-gray-700">Description</TableHead>
							<TableHead className="w-30 font-medium text-gray-700">Status</TableHead>
							<TableHead className="w-30 font-medium text-gray-700 text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{isLoading && (
							<TableRow>
								<TableCell colSpan={5} className="text-center py-8 text-gray-500">
									<div className="flex items-center justify-center">
										<RiLoader4Line className="w-5 h-5 animate-spin mr-2" />
										Loading knowledge base...
									</div>
								</TableCell>
							</TableRow>
						)}

						{isError && (
							<TableRow>
								<TableCell colSpan={5} className="text-center py-8 text-red-500">
									Failed to load knowledge base documents.
								</TableCell>
							</TableRow>
						)}

						{!isLoading && !isError && filteredList?.length === 0 && (
							<TableRow>
								<TableCell colSpan={5} className="text-center py-8 text-gray-500">
									No knowledge base documents found.
								</TableCell>
							</TableRow>
						)}

						{!isLoading &&
							filteredList?.map((row) => (
								<TableRow
									key={row.id}
									className="hover:bg-gray-50/60 cursor-pointer"
									onClick={() => router.push(`${basePath}/${row.id}`)}
								>
									<TableCell>
										<div className="flex items-center gap-3">
											<Avatar className="w-10 h-10 rounded-md after:rounded-md">
												<AvatarImage
													src="/mini-placeholder.svg"
													alt={row.title}
													className="object-cover rounded-md"
												/>
												<AvatarFallback className="rounded-md bg-blue-50 text-blue-600 font-semibold text-xs">
													{row.type?.substring(0, 2) || "KB"}
												</AvatarFallback>
											</Avatar>
											<div className="flex flex-col">
												<span className="font-medium text-gray-900 line-clamp-1">{row.title}</span>
												<span className="text-xs text-gray-500">{row.file_name}</span>
											</div>
										</div>
									</TableCell>
									<TableCell>
										<Badge
											variant="secondary"
											className="bg-gray-100 text-gray-700 hover:bg-gray-100"
										>
											{row.type}
										</Badge>
									</TableCell>
									<TableCell className="max-w-xl">
										<p className="text-sm text-gray-600 line-clamp-3 leading-relaxed">
											{row.ai_summary || row.content || "No description available."}
										</p>
									</TableCell>
									<TableCell>{getStatusBadge(row.status)}</TableCell>
									<TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
										<div className="flex justify-end gap-2">
											<Button
												onClick={() => router.push(`${basePath}/${row.id}`)}
												variant="outline"
												size="md"
												className="border-gray-200 font-medium"
											>
												<RiEyeLine className="mr-2 h-4 w-4" />
												View
											</Button>
											{hasDeleteAccess && (
												<Button
													onClick={() => {
														if (confirm(`Are you sure you want to delete "${row.title}"?`)) {
															deleteMutation.mutate(row.id);
														}
													}}
													disabled={deleteMutation.isPending}
													variant="outline"
													size="md"
													className="border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50 font-medium"
													title="Delete document"
												>
													<RiDeleteBin7Line className="h-4 w-4" />
												</Button>
											)}
										</div>
									</TableCell>
								</TableRow>
							))}
					</TableBody>
				</Table>
			</div>
		</div>
	);
}
