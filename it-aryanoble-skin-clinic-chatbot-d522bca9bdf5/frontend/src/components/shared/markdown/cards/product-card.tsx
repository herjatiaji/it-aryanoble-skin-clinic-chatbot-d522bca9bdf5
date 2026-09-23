import React, { useState } from "react";
import { RiCloseLine, RiZoomInLine } from "@remixicon/react";
import type { CardData, KeyValueItem } from "../types";
import { isValidImageUrl, resolveImageUrl } from "../utils";
import { ImagePreviewDialog } from "@/components/shared/image-preview-dialog";

export function ProductCard({
	data,
	onDeleteImage,
}: {
	data: CardData;
	onDeleteImage?: (src: string, alt: string) => void;
}) {
	const [isPreviewOpen, setIsPreviewOpen] = useState(false);
	const [imageError, setImageError] = useState(false);
	const { imageUrl, rawImageUrl, imageAlt, items } = data;

	let productName = "";
	let brand = "";
	let variant = "";
	let productType = "";
	let skinTypes = "";
	let netContent = "";
	let price = "";
	let sku = "";
	let bpom = "";
	let texture = "";
	let usage = "";
	let ageGroup = "";
	let sideEffects = "";
	let composition = "";
	let contraindications = "";
	let description = "";
	const otherItems: KeyValueItem[] = [];

	for (const item of items) {
		const k = item.key.toLowerCase();
		if (k.includes("product name") || k.includes("nama produk") || k === "nama" || k === "produk" || k === "product" || k.includes("produk")) {
			productName = item.value;
		} else if (k.includes("brand") || k.includes("merek")) {
			brand = item.value;
		} else if (k.includes("variant") || k.includes("varian")) {
			variant = item.value;
		} else if (
			k.includes("product type") ||
			k.includes("tipe produk") ||
			k.includes("jenis produk") ||
			k.includes("kategori") ||
			k.includes("category")
		) {
			productType = item.value;
		} else if (
			k.includes("skin type") ||
			k.includes("jenis kulit") ||
			k.includes("target kondisi")
		) {
			skinTypes = item.value;
		} else if (
			k.includes("net content") ||
			k.includes("berat bersih") ||
			k.includes("volume") ||
			k.includes("isi bersih") ||
			k.includes("ukuran") ||
			k.includes("size")
		) {
			netContent = item.value;
		} else if (k.includes("harga") || k.includes("price")) {
			price = item.value;
		} else if (k.includes("sku") || k.includes("kode sku")) {
			sku = item.value;
		} else if (k.includes("bpom") || k.includes("registrasi")) {
			bpom = item.value;
		} else if (k.includes("tekstur") || k.includes("texture") || k.includes("sediaan")) {
			texture = item.value;
		} else if (k.includes("aturan pakai") || k.includes("cara pakai") || k.includes("dosis") || k.includes("cara penggunaan")) {
			usage = item.value;
		} else if (k.includes("komposisi") || k.includes("composition") || k.includes("ingredients") || k.includes("kandungan")) {
			composition = item.value;
		} else if (k.includes("kontraindikasi") || k.includes("contraindication")) {
			contraindications = item.value;
		} else if (k.includes("target usia") || k.includes("usia") || k.includes("age")) {
			ageGroup = item.value;
		} else if (k.includes("efek samping") || k.includes("side effect")) {
			sideEffects = item.value;
		} else if (
			k.includes("deskripsi") ||
			k.includes("description") ||
			k.includes("ringkasan") ||
			k.includes("manfaat")
		) {
			description = item.value;
		} else {
			otherItems.push(item);
		}
	}

	if (!productName && imageAlt && !/^(?:product|foto produk|image|document image|gambar)$/i.test(imageAlt.trim())) {
		productName = imageAlt.trim();
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
							alt={imageAlt || productName || "Product"}
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
									onDeleteImage(rawImageUrl || imageUrl || "", imageAlt || productName || "");
								}}
								className="absolute top-1.5 right-1.5 z-10 size-6 flex items-center justify-center rounded-full bg-red-600 hover:bg-red-700 text-white shadow-sm cursor-pointer transition-transform hover:scale-110"
								title="Hapus gambar produk ini"
							>
								<RiCloseLine className="size-3.5" />
							</button>
						)}
					</div>

					<ImagePreviewDialog
						src={cleanImgUrl}
						alt={productName || imageAlt || "Product"}
						isOpen={isPreviewOpen}
						onOpenChange={setIsPreviewOpen}
					/>
				</>
			)}

			<div className="flex-1 min-w-0 flex flex-col justify-between self-stretch">
				<div className="flex flex-col gap-1 text-xs sm:text-sm text-zinc-900 leading-normal">
					{/* 1. Product Title */}
					{productName && (
						<h4 className="text-sm font-semibold text-zinc-950 leading-snug tracking-tight">
							{productName}
						</h4>
					)}

					{/* 2. SKU / Brand / Product Type / Variant Badges */}
					{(sku || brand || productType || variant) && (
						<div className="flex items-center gap-1.5 flex-wrap my-0.5">
							{sku ? (
								<span className="text-xs font-mono font-medium text-zinc-800 bg-zinc-100 px-2 py-0.5 rounded border border-zinc-200">
									SKU: {sku}
								</span>
							) : brand ? (
								<span className="text-xs font-medium text-zinc-800 bg-zinc-100 px-2 py-0.5 rounded border border-zinc-200">
									{brand}
								</span>
							) : null}
							{productType && (
								<span className="text-xs font-normal text-zinc-700 bg-zinc-100 px-2 py-0.5 rounded border border-zinc-200/80">
									{productType}
								</span>
							)}
							{variant && (
								<span className="text-xs font-normal text-zinc-700 bg-zinc-100 px-2 py-0.5 rounded border border-zinc-200/80">
									{variant}
								</span>
							)}
						</div>
					)}

					{/* 3. Net Content / Ukuran */}
					{netContent && (
						<div>
							<span className="text-zinc-500 font-medium">Ukuran:</span>{" "}
							<span className="text-zinc-900 font-normal">{netContent}</span>
						</div>
					)}

					{/* 4. Skin Types */}
					{skinTypes && (
						<div>
							<span className="text-zinc-500 font-medium">Skin Types:</span>{" "}
							<span className="text-zinc-900 font-normal">{skinTypes}</span>
						</div>
					)}

					{/* 5. Tekstur / Sediaan */}
					{texture && (
						<div>
							<span className="text-zinc-500 font-medium">Tekstur:</span>{" "}
							<span className="text-zinc-900 font-normal">{texture}</span>
						</div>
					)}

					{/* 6. Aturan Pakai */}
					{usage && (
						<div>
							<span className="text-zinc-500 font-medium">Aturan Pakai:</span>{" "}
							<span className="text-zinc-900 font-normal">{usage}</span>
						</div>
					)}

					{/* 7. Target Usia */}
					{ageGroup && (
						<div>
							<span className="text-zinc-500 font-medium">Target Usia:</span>{" "}
							<span className="text-zinc-900 font-normal">{ageGroup}</span>
						</div>
					)}

					{/* 8. No BPOM */}
					{bpom && (
						<div>
							<span className="text-zinc-500 font-medium">No BPOM:</span>{" "}
							<span className="font-mono text-zinc-800 text-xs bg-zinc-100 px-1.5 py-0.5 rounded border border-zinc-200">
								{bpom}
							</span>
						</div>
					)}

					{/* 9. Efek Samping */}
					{sideEffects && (
						<div>
							<span className="text-zinc-500 font-medium">Efek Samping:</span>{" "}
							<span className="text-zinc-900 font-normal">{sideEffects}</span>
						</div>
					)}

					{/* 10. Komposisi */}
					{composition && (
						<div>
							<span className="text-zinc-500 font-medium">Komposisi:</span>{" "}
							<span className="text-zinc-900 font-normal">{composition}</span>
						</div>
					)}

					{/* 11. Kontraindikasi */}
					{contraindications && (
						<div>
							<span className="text-zinc-500 font-medium">Kontraindikasi:</span>{" "}
							<span className="text-zinc-900 font-normal">{contraindications}</span>
						</div>
					)}

					{/* 12. Description / Deskripsi */}
					{description && (
						<div className="mt-1 text-zinc-600 text-xs sm:text-[13px] leading-relaxed">
							{description}
						</div>
					)}

					{/* 11. Other custom items */}
					{otherItems.map((item, idx) => (
						<div key={idx}>
							<span className="text-zinc-500 font-medium">{item.key}:</span>{" "}
							<span className="text-zinc-900 font-normal">{item.value}</span>
						</div>
					))}
				</div>

				{/* Price & SKU footer */}
				{(price || sku) && (
					<div className="mt-2 pt-1 border-t border-zinc-100 flex items-center justify-between flex-wrap gap-2">
						{price && <span className="text-sm font-bold text-zinc-950">{price}</span>}
						{sku && <span className="text-xs font-mono font-normal text-zinc-500">SKU: {sku}</span>}
					</div>
				)}
			</div>
		</div>
	);
}
