"use client";

import * as React from "react";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
	DialogDescription,
} from "@/components/ui/dialog";
import { RiImageLine } from "@remixicon/react";

export interface ImagePreviewDialogProps {
	src?: string;
	alt?: string;
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
}

export function ImagePreviewDialog({
	src,
	alt,
	isOpen,
	onOpenChange,
}: ImagePreviewDialogProps) {
	if (!src) return null;

	const displayName = alt && alt.trim() ? alt : "Image Preview";

	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent
				className="max-w-[95vw] sm:max-w-2xl md:max-w-4xl p-0 overflow-hidden bg-white border border-zinc-200/80 shadow-2xl rounded-xl gap-0 flex flex-col"
				showCloseButton={true}
			>
				<DialogHeader className="px-4 sm:px-5 py-3 border-b border-zinc-100 flex flex-row items-center justify-between gap-3 bg-zinc-50/70 shrink-0">
					<div className="flex items-center gap-2.5 min-w-0 pr-8">
						<span className="p-1 rounded-md bg-blue-50 text-blue-600 shrink-0">
							<RiImageLine className="size-4" />
						</span>
						<div className="flex flex-col min-w-0">
							<DialogTitle className="text-sm font-semibold text-zinc-900 truncate">
								{displayName}
							</DialogTitle>
							<DialogDescription className="sr-only">
								{displayName}
							</DialogDescription>
						</div>
					</div>
				</DialogHeader>

				<div className="relative w-full max-h-[75vh] flex items-center justify-center p-3 sm:p-6 bg-zinc-950/5 overflow-auto">
					{/* eslint-disable-next-line @next/next/no-img-element */}
					<img
						src={src}
						alt={displayName}
						className="max-w-full max-h-[65vh] w-auto h-auto object-contain rounded-md shadow-xs"
					/>
				</div>
			</DialogContent>
		</Dialog>
	);
}
