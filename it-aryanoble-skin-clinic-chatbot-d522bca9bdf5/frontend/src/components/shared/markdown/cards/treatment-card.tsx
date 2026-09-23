import React, { useState } from "react";
import { RiCloseLine, RiZoomInLine } from "@remixicon/react";
import type { CardData, KeyValueItem } from "../types";
import { isValidImageUrl, resolveImageUrl } from "../utils";
import { ImagePreviewDialog } from "@/components/shared/image-preview-dialog";

export function TreatmentCard({
	data,
	onDeleteImage,
}: {
	data: CardData;
	onDeleteImage?: (src: string, alt: string) => void;
}) {
	const [isPreviewOpen, setIsPreviewOpen] = useState(false);
	const [imageError, setImageError] = useState(false);
	const { imageUrl, rawImageUrl, imageAlt, items } = data;

	let treatmentName = "";
	let category = "";
	let duration = "";
	let downtime = "";
	let anesthesia = "";
	let indications = "";
	let price = "";
	let interval = "";
	let sideEffects = "";
	const otherItems: KeyValueItem[] = [];

	for (const item of items) {
		const k = item.key.toLowerCase();
		if (
			k.includes("treatment name") ||
			k.includes("nama tindakan") ||
			k.includes("nama treatment")
		) {
			treatmentName = item.value;
		} else if (k.includes("category") || k.includes("kategori") || k.includes("tipe")) {
			category = item.value;
		} else if (k.includes("duration") || k.includes("durasi") || k.includes("waktu")) {
			duration = item.value;
		} else if (k.includes("downtime") || k.includes("pemulihan")) {
			downtime = item.value;
		} else if (k.includes("anestesi") || k.includes("anesthesia")) {
			anesthesia = item.value;
		} else if (k.includes("indikasi") || k.includes("target") || k.includes("skin type")) {
			indications = item.value;
		} else if (k.includes("harga") || k.includes("price") || k.includes("biaya")) {
			price = item.value;
		} else if (k.includes("interval") || k.includes("sesi") || k.includes("frekuensi")) {
			interval = item.value;
		} else if (k.includes("efek samping") || k.includes("side effect")) {
			sideEffects = item.value;
		} else {
			otherItems.push(item);
		}
	}

	const cleanImgUrl = imageUrl && isValidImageUrl(imageUrl) ? resolveImageUrl(imageUrl) : undefined;

	return (
		<div className="not-prose my-2.5 rounded-lg border border-zinc-200/80 bg-white p-3.5 flex flex-col sm:flex-row gap-3.5 items-start shadow-none">
			{cleanImgUrl && !imageError && (
				<>
					<div
						className="size-28 sm:size-32 shrink-0 bg-zinc-50 rounded-lg border border-zinc-200/80 p-2 flex items-center justify-center overflow-hidden relative group cursor-pointer"
						onClick={() => setIsPreviewOpen(true)}
					>
						{/* eslint-disable-next-line @next/next/no-img-element */}
						<img
							src={cleanImgUrl}
							alt={imageAlt || treatmentName || "Treatment"}
							className="size-full object-contain"
							loading="lazy"
							onError={() => {
								setImageError(true);
							}}
						/>
						<button
							type="button"
							onClick={(e) => {
								e.stopPropagation();
								setIsPreviewOpen(true);
							}}
							className="absolute bottom-1.5 right-1.5 p-1 rounded-md bg-white/95 text-zinc-600 border border-zinc-200/80 opacity-0 group-hover:opacity-100 transition-opacity shadow-xs cursor-pointer"
							title="View image"
						>
							<RiZoomInLine className="size-3.5" />
						</button>
						{onDeleteImage && (
							<button
								type="button"
								onClick={(e) => {
									e.stopPropagation();
									e.preventDefault();
									onDeleteImage(rawImageUrl || imageUrl || "", imageAlt || treatmentName || "");
								}}
								className="absolute top-1.5 right-1.5 z-10 size-6 flex items-center justify-center rounded-full bg-red-600 hover:bg-red-700 text-white shadow-sm cursor-pointer transition-transform hover:scale-110"
								title="Hapus gambar tindakan ini"
							>
								<RiCloseLine className="size-3.5" />
							</button>
						)}
					</div>

					<ImagePreviewDialog
						src={cleanImgUrl}
						alt={treatmentName || imageAlt || "Treatment"}
						isOpen={isPreviewOpen}
						onOpenChange={setIsPreviewOpen}
					/>
				</>
			)}

			<div className="flex-1 min-w-0 flex flex-col justify-between self-stretch">
				<div className="flex flex-col gap-1 text-xs sm:text-sm text-zinc-900 leading-normal">
					{/* Treatment Title */}
					{treatmentName && (
						<h4 className="text-sm font-semibold text-zinc-950 leading-snug tracking-tight">
							{treatmentName}
						</h4>
					)}

					{/* Category Badge */}
					{category && (
						<div className="flex items-center gap-1.5 flex-wrap my-0.5">
							<span className="text-xs font-medium text-zinc-800 bg-zinc-100 px-2 py-0.5 rounded border border-zinc-200">
								{category}
							</span>
						</div>
					)}

					{/* 3. Single-column Specifications */}
					{duration && (
						<div>
							<span className="text-zinc-500 font-medium">Durasi:</span>{" "}
							<span className="text-zinc-900 font-normal">{duration}</span>
						</div>
					)}

					{downtime && (
						<div>
							<span className="text-zinc-500 font-medium">Downtime:</span>{" "}
							<span className="text-zinc-900 font-normal">{downtime}</span>
						</div>
					)}

					{anesthesia && (
						<div>
							<span className="text-zinc-500 font-medium">Anestesi:</span>{" "}
							<span className="text-zinc-900 font-normal">{anesthesia}</span>
						</div>
					)}

					{/* Target Indikasi */}
					{indications && (
						<div>
							<span className="text-zinc-500 font-medium">Indikasi:</span>{" "}
							<span className="text-zinc-900 font-normal">{indications}</span>
						</div>
					)}

					{/* Sesi Interval */}
					{interval && (
						<div>
							<span className="text-zinc-500 font-medium">Sesi Disarankan:</span>{" "}
							<span className="text-zinc-900 font-normal">{interval}</span>
						</div>
					)}

					{/* Efek Samping */}
					{sideEffects && (
						<div>
							<span className="text-zinc-500 font-medium">Efek Samping:</span>{" "}
							<span className="text-zinc-900 font-normal">{sideEffects}</span>
						</div>
					)}

					{/* Other custom items */}
					{otherItems.map((item, idx) => (
						<div key={idx}>
							<span className="text-zinc-500 font-medium">{item.key}:</span>{" "}
							<span className="text-zinc-900 font-normal">{item.value}</span>
						</div>
					))}
				</div>

				{/* Price Footer */}
				{price && (
					<div className="mt-2 pt-1 border-t border-zinc-100 flex items-center justify-between flex-wrap gap-2">
						<span className="text-sm font-bold text-zinc-950">{price}</span>
						<span className="text-xs text-zinc-500 font-normal">Estimasi per sesi</span>
					</div>
				)}
			</div>
		</div>
	);
}
