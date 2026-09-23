import React, { useState } from "react";
import { RiZoomInLine } from "@remixicon/react";
import type { BeforeAfterData } from "../types";
import { ImagePreviewDialog } from "@/components/shared/image-preview-dialog";

export function BeforeAfterCard({ data }: { data: BeforeAfterData }) {
	const { beforeImage, afterImage } = data;
	const [previewState, setPreviewState] = useState<{
		isOpen: boolean;
		url: string;
		alt: string;
	}>({
		isOpen: false,
		url: "",
		alt: "",
	});
	const [beforeError, setBeforeError] = useState(false);
	const [afterError, setAfterError] = useState(false);

	const showBefore = Boolean(beforeImage?.url && !beforeError);
	const showAfter = Boolean(afterImage?.url && !afterError);

	if (!showBefore && !showAfter) {
		return null;
	}

	return (
		<>
			<div className="not-prose my-2.5 flex flex-col sm:flex-row gap-2.5 items-stretch w-full max-w-2xl">
				{/* Left / Before Image */}
				{showBefore && (
					<span className="flex-1 min-w-35 max-w-full rounded-lg border border-zinc-200/80 bg-zinc-50/60 overflow-hidden align-top inline-flex flex-col shadow-none">
						<span className="h-44 sm:h-48 w-full p-2 flex items-center justify-center overflow-hidden relative group cursor-pointer">
							{/* eslint-disable-next-line @next/next/no-img-element */}
							<img
								src={beforeImage.url}
								alt={beforeImage.alt || "Sebelum Perawatan"}
								className="size-full object-contain block"
								loading="lazy"
								onClick={() => {
									if (beforeImage.url) {
										setPreviewState({
											isOpen: true,
											url: beforeImage.url,
											alt: beforeImage.alt || "Sebelum Perawatan",
										});
									}
								}}
								onError={() => {
									setBeforeError(true);
								}}
							/>
							<button
								type="button"
								onClick={(e) => {
									e.stopPropagation();
									if (beforeImage.url) {
										setPreviewState({
											isOpen: true,
											url: beforeImage.url,
											alt: beforeImage.alt || "Sebelum Perawatan",
										});
									}
								}}
								className="absolute bottom-1.5 right-1.5 p-1 rounded-md bg-white/95 text-zinc-600 border border-zinc-200/80 opacity-0 group-hover:opacity-100 transition-opacity shadow-xs cursor-pointer"
								title="View image"
							>
								<RiZoomInLine className="size-3.5" />
							</button>
						</span>
						{beforeImage.alt && (
							<span className="block px-2.5 py-1.5 text-xs text-zinc-700 font-medium bg-white border-t border-zinc-200/70 truncate w-full text-center">
								{beforeImage.alt}
							</span>
						)}
					</span>
				)}

				{/* Right / After Image */}
				{showAfter && (
					<span className="flex-1 min-w-35 max-w-full rounded-lg border border-zinc-200/80 bg-zinc-50/60 overflow-hidden align-top inline-flex flex-col shadow-none">
						<span className="h-44 sm:h-48 w-full p-2 flex items-center justify-center overflow-hidden relative group cursor-pointer">
							{/* eslint-disable-next-line @next/next/no-img-element */}
							<img
								src={afterImage.url}
								alt={afterImage.alt || "Sesudah Perawatan"}
								className="size-full object-contain block"
								loading="lazy"
								onClick={() => {
									if (afterImage.url) {
										setPreviewState({
											isOpen: true,
											url: afterImage.url,
											alt: afterImage.alt || "Sesudah Perawatan",
										});
									}
								}}
								onError={() => {
									setAfterError(true);
								}}
							/>
							<button
								type="button"
								onClick={(e) => {
									e.stopPropagation();
									if (afterImage.url) {
										setPreviewState({
											isOpen: true,
											url: afterImage.url,
											alt: afterImage.alt || "Sesudah Perawatan",
										});
									}
								}}
								className="absolute bottom-1.5 right-1.5 p-1 rounded-md bg-white/95 text-zinc-600 border border-zinc-200/80 opacity-0 group-hover:opacity-100 transition-opacity shadow-xs cursor-pointer"
								title="View image"
							>
								<RiZoomInLine className="size-3.5" />
							</button>
						</span>
						{afterImage.alt && (
							<span className="block px-2.5 py-1.5 text-xs text-zinc-700 font-medium bg-white border-t border-zinc-200/70 truncate w-full text-center">
								{afterImage.alt}
							</span>
						)}
					</span>
				)}
			</div>

			<ImagePreviewDialog
				src={previewState.url}
				alt={previewState.alt}
				isOpen={previewState.isOpen}
				onOpenChange={(open) => setPreviewState((prev) => ({ ...prev, isOpen: open }))}
			/>
		</>
	);
}
