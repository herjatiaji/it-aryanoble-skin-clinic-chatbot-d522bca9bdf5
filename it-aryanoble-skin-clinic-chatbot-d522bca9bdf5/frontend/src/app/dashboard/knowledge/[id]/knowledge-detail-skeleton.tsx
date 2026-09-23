"use client";

import { Skeleton } from "@/components/ui/skeleton";

export function KnowledgeDetailSkeleton() {
	return (
		<div className="flex flex-col h-[calc(100vh-65px)] w-full bg-white relative animate-pulse">
			{/* Title Header with Actions Skeleton */}
			<div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 shrink-0 bg-white justify-between">
				<div className="flex items-center gap-3 flex-1 min-w-0 max-w-xl">
					<Skeleton className="size-9 rounded-lg shrink-0" />
					<Skeleton className="h-5 w-56 rounded" />
					<Skeleton className="h-6 w-28 rounded-md" />
				</div>
				<div className="flex items-center gap-2">
					<Skeleton className="h-10 w-32 rounded-lg" />
					<Skeleton className="h-10 w-36 rounded-lg" />
				</div>
			</div>

			{/* Main Chat / Processing Area */}
			<div className="flex flex-col flex-1 overflow-hidden">
				{/* Scrollable Message Viewport */}
				<div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 max-w-5xl mx-auto w-full">
					{/* Attached Document Pill (Right-aligned) */}
					<div className="flex justify-end">
						<Skeleton className="h-12 w-52 rounded-lg" />
					</div>

					{/* Pipeline Processing Card */}
					<div className="flex items-start gap-3 w-full">
						<Skeleton className="size-8 rounded-lg shrink-0" />
						<div className="flex-1 p-4 rounded-lg border border-blue-200/70 bg-blue-50/40 space-y-4">
							{/* File Metadata Skeleton */}
							<div className="flex items-center gap-2.5 p-2.5 bg-white/90 rounded-lg border border-blue-100">
								<Skeleton className="size-8 rounded-md shrink-0" />
								<div className="space-y-1 flex-1">
									<Skeleton className="h-3.5 w-44 rounded" />
									<Skeleton className="h-2.5 w-32 rounded" />
								</div>
							</div>

							{/* Timer & Status Bar */}
							<div className="flex items-center justify-between border-b border-blue-100 pb-3">
								<div className="flex items-center gap-2">
									<Skeleton className="size-3 rounded-full" />
									<Skeleton className="h-4 w-48 rounded" />
								</div>
								<Skeleton className="h-6 w-20 rounded-md" />
							</div>

							{/* Progress Bar */}
							<div className="space-y-1.5">
								<div className="flex justify-between">
									<Skeleton className="h-3 w-36 rounded" />
									<Skeleton className="h-3 w-10 rounded" />
								</div>
								<Skeleton className="h-1.5 w-full rounded-full" />
							</div>

							{/* 4 Steps */}
							<div className="space-y-2 bg-white/80 p-3 rounded-lg border border-blue-100">
								<Skeleton className="h-8 w-full rounded-md" />
								<Skeleton className="h-8 w-full rounded-md" />
								<Skeleton className="h-8 w-full rounded-md" />
								<Skeleton className="h-8 w-full rounded-md" />
							</div>
						</div>
					</div>
				</div>

				{/* Bottom Input Box */}
				<div className="px-6 sm:px-8 py-4 shrink-0 w-full">
					<div className="max-w-5xl mx-auto rounded-lg p-4 flex flex-col gap-3 border border-zinc-200 bg-white">
						<Skeleton className="h-4 w-1/2 rounded" />
						<div className="flex items-center justify-between pt-1">
							<Skeleton className="size-8 rounded-md" />
							<Skeleton className="size-8 rounded-lg" />
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
