"use client";

import { Button } from "@/components/ui/button";
import { MarkdownContent } from "@/components/shared/markdown-content";
import { cn } from "@/lib/utils";
import {
	RiArrowDownSLine,
	RiArrowUpSLine,
	RiCheckLine,
	RiEyeLine,
	RiFileCopyLine,
	RiSparklingLine,
} from "@remixicon/react";
import { useState } from "react";
import { toast } from "sonner";

interface BatchExecutiveSummaryProps {
	summary: string;
	documentCount?: number;
	className?: string;
	isExpanded?: boolean;
	onToggleExpand?: () => void;
	onSetVisibility?: () => void;
	hasWriteAccess?: boolean;
}

export function BatchExecutiveSummary({
	summary,
	documentCount,
	className,
	isExpanded: propIsExpanded,
	onToggleExpand,
	onSetVisibility,
	hasWriteAccess,
}: BatchExecutiveSummaryProps) {
	const [internalIsExpanded, setInternalIsExpanded] = useState(true);
	const [hasCopied, setHasCopied] = useState(false);

	const isExpanded = propIsExpanded !== undefined ? propIsExpanded : internalIsExpanded;
	const handleToggle = onToggleExpand || (() => setInternalIsExpanded((prev) => !prev));

	const handleCopy = async () => {
		try {
			await navigator.clipboard.writeText(summary);
			setHasCopied(true);
			toast.success("Executive summary copied to clipboard");
			setTimeout(() => setHasCopied(false), 2000);
		} catch {
			toast.error("Failed to copy summary");
		}
	};

	return (
		<div className={cn("bg-zinc-100/50 rounded-lg p-4 w-full text-zinc-950", className)}>
			{/* Header */}
			<div className="flex items-center justify-between gap-3 mb-2">
				<div className="flex items-center gap-2 min-w-0">
					<RiSparklingLine className="size-5 text-blue-600 shrink-0" />
					<div className="flex items-center gap-2 min-w-0">
						<h3 className="font-semibold text-sm">Executive Summary</h3>
						{typeof documentCount === "number" && documentCount > 0 && (
							<span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-zinc-200/60 text-zinc-600 shrink-0">
								{documentCount} {documentCount === 1 ? "document" : "documents"}
							</span>
						)}
					</div>
				</div>

				{/* Actions */}
				<div className="flex items-center gap-1 shrink-0">
					<Button
						variant="ghost"
						size="sm"
						onClick={handleCopy}
						className="h-7 px-2 text-xs text-zinc-600 hover:text-zinc-900 hover:bg-zinc-200/50 rounded-md gap-1 font-normal cursor-pointer"
						title="Copy summary"
					>
						{hasCopied ? (
							<>
								<RiCheckLine className="size-3.5 text-emerald-600" />
								<span className="text-[11px] text-emerald-600 font-medium">Copied</span>
							</>
						) : (
							<>
								<RiFileCopyLine className="size-3.5" />
								<span className="text-[11px] hidden sm:inline">Copy</span>
							</>
						)}
					</Button>
					<Button
						variant="ghost"
						size="icon"
						onClick={handleToggle}
						className="size-7 text-zinc-500 hover:text-zinc-900 hover:bg-zinc-200/50 rounded-md cursor-pointer"
						title={isExpanded ? "Collapse summary" : "Expand summary"}
					>
						{isExpanded ? (
							<RiArrowUpSLine className="size-4" />
						) : (
							<RiArrowDownSLine className="size-4" />
						)}
					</Button>
				</div>
			</div>

			<p className="text-xs text-zinc-500 mb-4">
				Synthesized overview and clinical takeaways extracted across this batch session.
			</p>

			{/* Collapsible Body */}
			{isExpanded && (
				<div className="pt-3 border-t border-zinc-200/60 text-xs sm:text-sm text-zinc-800 leading-normal overflow-hidden">
					<MarkdownContent content={summary} />
				</div>
			)}

			{/* Bottom Action Footer for Batch Settings */}
			{onSetVisibility && hasWriteAccess && (
				<div className="mt-3 pt-3 border-t border-zinc-200/60 flex flex-wrap items-center justify-between gap-3">
					<span className="text-xs sm:text-sm text-zinc-600 font-medium">
						Set branch, doctor type, or doctor access limits for all documents in this batch:
					</span>
					<Button
						type="button"
						size="default"
						variant="default"
						onClick={onSetVisibility}
						className="gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none shrink-0"
					>
						<RiEyeLine className="size-4" />
						Set Visibility
					</Button>
				</div>
			)}
		</div>
	);
}
