"use client";

import React, { useEffect, useState } from "react";
import {
	RiCheckLine,
	RiLoader4Line,
	RiRobot2Line,
	RiTimeLine,
	RiSparklingLine,
} from "@remixicon/react";
import { cn } from "@/lib/utils";
import { getFileIconAndColor } from "@/app/dashboard/ingest/utils/prompt-input-utils";

interface ProcessingPipelineCardProps {
	headerNode?: React.ReactNode;
	fileName?: string | null;
}

interface StepItem {
	title: string;
	description: string;
	minSeconds: number;
}

const PIPELINE_STEPS: StepItem[] = [
	{
		title: "Document Extraction & Layout OCR",
		description: "Extracting text, multi-column tables, and visual structure from the source file",
		minSeconds: 0,
	},
	{
		title: "Semantic Chunking & Entity Extraction",
		description: "Partitioning document into contextual chunks and identifying clinical terminology",
		minSeconds: 3,
	},
	{
		title: "AI Executive Summary Synthesis",
		description: "Analyzing clinical content and synthesizing structured knowledge review draft",
		minSeconds: 7,
	},
	{
		title: "Staging Draft Finalization & Vector Indexing",
		description: "Staging document for review and embedding into PGVector search index",
		minSeconds: 12,
	},
];

export function ProcessingPipelineCard({ headerNode, fileName }: ProcessingPipelineCardProps) {
	const [elapsedSeconds, setElapsedSeconds] = useState(0);

	useEffect(() => {
		const interval = setInterval(() => {
			setElapsedSeconds((prev) => prev + 1);
		}, 1000);
		return () => clearInterval(interval);
	}, []);

	// Determine active step based on elapsed time
	const activeStepIndex =
		elapsedSeconds < 3 ? 0 : elapsedSeconds < 7 ? 1 : elapsedSeconds < 12 ? 2 : 3;

	// Calculate smooth progress percentage
	const progressPercent = Math.min(
		95,
		Math.max(
			12,
			activeStepIndex === 0
				? 20 + elapsedSeconds * 5
				: activeStepIndex === 1
					? 45 + (elapsedSeconds - 3) * 6
					: activeStepIndex === 2
						? 75 + (elapsedSeconds - 7) * 3
						: 90 + Math.min(5, (elapsedSeconds - 12) * 0.5),
		),
	);

	const formatTime = (totalSec: number) => {
		const m = Math.floor(totalSec / 60);
		const s = totalSec % 60;
		return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
	};

	const { Icon: FileIcon, bgColor: fileBgColor, textColor: fileTextColor } = getFileIconAndColor(
		fileName,
	);
	const extName = fileName?.includes(".")
		? fileName.split(".").pop()?.toUpperCase() || "DOC"
		: "DOC";

	return (
		<div className="flex items-start gap-3 w-full min-w-0 max-w-full animate-in fade-in duration-300">
			{/* AI Avatar */}
			<div className="bg-blue-600 rounded-lg text-white flex items-center justify-center p-2 mt-0.5 shrink-0 shadow-none">
				<RiRobot2Line className="size-4" />
			</div>

			{/* Main Processing Card */}
			<div className="bg-blue-50/70 text-zinc-950 p-4 rounded-lg text-sm w-full min-w-0 max-w-full border border-blue-200/70 flex flex-col gap-3.5 shadow-none overflow-hidden">
				{headerNode}

				{/* File Metadata Header */}
				{fileName && (
					<div className="flex items-center gap-2.5 p-2.5 bg-white/95 rounded-lg border border-blue-200/80 shadow-none">
						<div className={cn(fileBgColor, fileTextColor, "p-2 rounded-md shrink-0")}>
							<FileIcon className="size-4" />
						</div>
						<div className="flex flex-col min-w-0 flex-1">
							<span className="text-xs font-semibold text-zinc-900 truncate" title={fileName}>
								{fileName}
							</span>
							<span className="text-[11px] text-zinc-500 font-medium">
								{extName} Document • Extraction & Indexing in Progress
							</span>
						</div>
					</div>
				)}

				{/* Top Status & Elapsed Timer */}
				<div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-100 pb-3">
					<div className="flex items-center gap-2">
						<span className="relative flex h-3 w-3">
							<span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
							<span className="relative inline-flex rounded-full h-3 w-3 bg-blue-600"></span>
						</span>
						<div className="flex items-center gap-1.5">
							<span className="font-semibold text-blue-900 text-sm">
								AI Ingestion Pipeline Active
							</span>
							<RiSparklingLine className="size-4 text-blue-600 animate-pulse" />
						</div>
					</div>

					<div className="flex items-center gap-1.5 px-2.5 py-1 bg-white/90 border border-blue-200 rounded-md text-xs font-mono font-medium text-blue-700 shadow-none">
						<RiTimeLine className="size-3.5 text-blue-600" />
						<span>⏱ {formatTime(elapsedSeconds)}</span>
					</div>
				</div>

				{/* Slim Top Progress Bar */}
				<div className="flex flex-col gap-1.5">
					<div className="flex items-center justify-between text-xs text-zinc-600">
						<span className="font-medium text-zinc-700">
							{PIPELINE_STEPS[activeStepIndex].title}
						</span>
						<span className="font-semibold text-blue-700 font-mono">
							{Math.round(progressPercent)}%
						</span>
					</div>
					<div className="w-full h-1.5 bg-blue-100/90 rounded-full overflow-hidden">
						<div
							className="h-full bg-blue-600 transition-all duration-500 ease-out rounded-full"
							style={{ width: `${progressPercent}%` }}
						/>
					</div>
				</div>

				{/* Detailed Multi-Step Status List */}
				<div className="flex flex-col gap-2 bg-white/90 rounded-lg border border-blue-100 p-3 text-xs text-zinc-700 shadow-none">
					{PIPELINE_STEPS.map((step, idx) => {
						const isDone = idx < activeStepIndex;
						const isCurrent = idx === activeStepIndex;
						const isPending = idx > activeStepIndex;

						return (
							<div
								key={idx}
								className={cn(
									"flex items-start gap-2.5 p-2 rounded-lg transition-colors",
									isCurrent && "bg-blue-50/70 border border-blue-200/60",
									isDone && "text-zinc-800",
									isPending && "text-zinc-400 opacity-70",
								)}
							>
								{/* Step Status Icon */}
								<div className="mt-0.5 shrink-0">
									{isDone ? (
										<div className="size-4 rounded-md bg-emerald-100 text-emerald-600 flex items-center justify-center">
											<RiCheckLine className="size-3 stroke-2" />
										</div>
									) : isCurrent ? (
										<RiLoader4Line className="size-4 animate-spin text-blue-600" />
									) : (
										<div className="size-4 rounded-md border border-zinc-300 flex items-center justify-center text-[10px] text-zinc-400 font-mono">
											{idx + 1}
										</div>
									)}
								</div>

								{/* Step Details */}
								<div className="flex flex-col gap-0.5 min-w-0">
									<span
										className={cn(
											"font-medium leading-tight",
											isCurrent && "text-blue-900 font-semibold",
											isDone && "text-zinc-800",
										)}
									>
										{step.title}
									</span>
									<span className="text-[11px] text-zinc-500 leading-snug">
										{step.description}
									</span>
								</div>
							</div>
						);
					})}
				</div>

				{/* Animated Shimmer Skeleton for Incoming Summary */}
				<div className="flex flex-col gap-2 bg-white/80 p-3.5 rounded-lg border border-blue-100 animate-pulse shadow-none">
					<div className="flex items-center gap-2 mb-1">
						<div className="h-3.5 bg-blue-200/70 rounded w-1/4" />
						<div className="h-3.5 bg-blue-100 rounded w-12" />
					</div>
					<div className="h-2.5 bg-blue-100 rounded w-full" />
					<div className="h-2.5 bg-blue-100 rounded w-11/12" />
					<div className="h-2.5 bg-blue-100 rounded w-4/5" />
				</div>

				{/* Footer Notice */}
				<div className="flex items-center justify-between text-[11px] text-zinc-500 pt-0.5">
					<span>Processing continues in the background if you navigate away.</span>
					<span className="font-medium text-blue-600">Auto-refreshing...</span>
				</div>
			</div>
		</div>
	);
}
