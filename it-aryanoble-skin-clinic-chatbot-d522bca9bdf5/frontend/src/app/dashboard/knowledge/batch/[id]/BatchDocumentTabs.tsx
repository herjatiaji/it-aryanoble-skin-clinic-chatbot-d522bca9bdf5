"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KnowledgeResponse } from "../../api/types";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import {
	RiFileExcel2Line,
	RiFilePdf2Line,
	RiFilePpt2Line,
	RiFileTextLine,
	RiFileWord2Line,
	RiImage2Line,
} from "@remixicon/react";

interface BatchDocumentTabsProps {
	documents: KnowledgeResponse[];
	activeId: string;
	onSelectDoc: (id: string) => void;
}

const getFileIconAndColor = (filename?: string | null) => {
	if (!filename)
		return { Icon: RiFileTextLine, textColor: "text-blue-600" };
	const ext = filename.split(".").pop()?.toLowerCase() || "";
	switch (ext) {
		case "pdf":
			return { Icon: RiFilePdf2Line, textColor: "text-red-600" };
		case "doc":
		case "docx":
			return { Icon: RiFileWord2Line, textColor: "text-blue-600" };
		case "xls":
		case "xlsx":
		case "csv":
			return { Icon: RiFileExcel2Line, textColor: "text-emerald-600" };
		case "ppt":
		case "pptx":
		case "pps":
		case "ppsx":
		case "pot":
		case "potx":
		case "odp":
			return { Icon: RiFilePpt2Line, textColor: "text-orange-600" };
		case "png":
		case "jpg":
		case "jpeg":
		case "gif":
		case "webp":
		case "svg":
			return { Icon: RiImage2Line, textColor: "text-purple-600" };
		case "txt":
		case "md":
		default:
			return { Icon: RiFileTextLine, textColor: "text-blue-600" };
	}
};

export function BatchDocumentTabs({
	documents,
	activeId,
	onSelectDoc,
}: BatchDocumentTabsProps) {
	const scrollContainerRef = useRef<HTMLDivElement>(null);

	// Auto-scroll active tab horizontally within its container without scrolling the page/viewport
	useEffect(() => {
		const el = scrollContainerRef.current;
		if (!el) return;
		const activeBtn = el.querySelector(`[data-tab-id="${activeId}"]`) as HTMLElement | null;
		if (activeBtn) {
			const left = activeBtn.offsetLeft - el.clientWidth / 2 + activeBtn.clientWidth / 2;
			el.scrollTo({ left, behavior: "smooth" });
		}
	}, [activeId]);

	const activeIndex = documents.findIndex((d) => d.id === activeId);
	const approvedCount = documents.filter((d) => (d.status || "").toUpperCase() === "APPROVED").length;
	const pendingCount = documents.filter((d) => (d.status || "").toUpperCase() === "PENDING").length;
	const processingCount = documents.filter((d) => (d.status || "").toUpperCase() === "PROCESSING").length;

	return (
		<div className="flex flex-col gap-2 w-full min-w-0 max-w-full">
			{/* Sub-header with document count and batch progress */}
			<div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
				<div className="flex items-center gap-2 min-w-0">
					<h4 className="text-xs font-semibold text-blue-900 uppercase tracking-wider truncate">
						Documents in this batch ({documents.length})
					</h4>
					<span className="text-xs text-zinc-600 font-normal shrink-0">
						• Viewing {activeIndex + 1} of {documents.length}
					</span>
				</div>

				<div className="flex items-center gap-1.5 text-xs font-medium bg-zinc-50 border border-zinc-200/80 px-2.5 py-1 rounded-md text-zinc-700 shrink-0">
					<span>
						<span className="font-semibold text-zinc-900">{approvedCount}</span> of{" "}
						<span className="font-semibold text-zinc-900">{documents.length}</span> Approved
					</span>
					{pendingCount > 0 && (
						<>
							<span className="text-zinc-300">•</span>
							<span className="text-amber-700">{pendingCount} On review</span>
						</>
					)}
					{processingCount > 0 && (
						<>
							<span className="text-zinc-300">•</span>
							<span className="text-blue-700">{processingCount} Processing</span>
						</>
					)}
				</div>
			</div>

			{/* Scrollable Tabs Bar */}
			<div
				ref={scrollContainerRef}
				className="w-full min-w-0 max-w-full overflow-x-auto overflow-y-hidden scroll-smooth pb-1.5 snap-x snap-mandatory [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar-track]:bg-zinc-100/80 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-thumb]:bg-zinc-300 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-zinc-400"
			>
				<Tabs value={activeId} onValueChange={onSelectDoc} className="w-full min-w-0 max-w-full">
					<TabsList
						variant="line"
						className="inline-flex w-max min-w-0 justify-start border-none pb-0 gap-2 bg-transparent"
					>
						{documents.map((tabDoc, tabIndex) => {
							const { Icon: TabIcon, textColor: tabTextColor } = getFileIconAndColor(
								tabDoc.file_name || tabDoc.title
							);
							return (
								<TabsTrigger
									key={tabDoc.id}
									value={tabDoc.id}
									data-tab-id={tabDoc.id}
									title={tabDoc.file_name || tabDoc.title || `Document ${tabIndex + 1}`}
									className="w-48 shrink-0 snap-start relative inline-flex items-center justify-between gap-1.5 font-medium text-xs text-zinc-700 hover:text-blue-700 data-active:text-blue-700 data-active:after:bg-blue-700 px-2.5 py-1.5 transition-all cursor-pointer"
								>
									<div className="flex items-center gap-1.5 min-w-0 flex-1">
										<TabIcon className={cn("size-3.5 shrink-0", tabTextColor)} />
										<span className="truncate text-left">
											{tabDoc.file_name || tabDoc.title || `Document ${tabIndex + 1}`}
										</span>
									</div>
									{tabDoc.status === "PROCESSING" && (
										<span
											className="size-2 rounded-full bg-blue-500 animate-pulse shrink-0 ml-1.5"
											title="Processing"
										/>
									)}
									{tabDoc.status === "PENDING" && (
										<span
											className="size-2 rounded-full bg-amber-500 shrink-0 ml-1.5"
											title="On Review"
										/>
									)}
									{tabDoc.status === "APPROVED" && (
										<span
											className="size-2 rounded-full bg-emerald-500 shrink-0 ml-1.5"
											title="Approved"
										/>
									)}
									{tabDoc.status === "REJECTED" && (
										<span
											className="size-2 rounded-full bg-red-500 shrink-0 ml-1.5"
											title="Failed / Rejected"
										/>
									)}
								</TabsTrigger>
							);
						})}
					</TabsList>
				</Tabs>
			</div>
		</div>
	);
}
