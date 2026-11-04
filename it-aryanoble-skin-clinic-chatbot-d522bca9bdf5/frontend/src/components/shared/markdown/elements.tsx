"use client";

import React, { createContext, useContext, useState } from "react";
import { RiCloseLine, RiZoomInLine } from "@remixicon/react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { extractNodeText, isValidImageUrl, resolveImageUrl } from "./utils";
import { ImagePreviewDialog } from "../image-preview-dialog";
import { MarkdownTable, MarkdownTbody } from "./markdown-table";

/**
 * True when rendering inside a table cell: images collapse to compact thumbnails
 * so product photos fit the cell instead of expanding to full card size.
 */
export const CompactImageContext = createContext(false);

function MarkdownImage({ src, alt, onDelete, ...props }: React.ComponentProps<"img"> & { onDelete?: (src: string, alt: string) => void }) {
	const [isOpen, setIsOpen] = useState(false);
	const [isHidden, setIsHidden] = useState(false);
	const isCompact = useContext(CompactImageContext);
	const strSrc = typeof src === "string" ? src.trim() : "";
	if (!isValidImageUrl(strSrc) || isHidden) {
		return null;
	}

	const resolvedSrc = resolveImageUrl(strSrc);
	const altText = typeof alt === "string" ? alt : "Document Image";

	const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
		try {
			const img = e.currentTarget;
			if (!img.naturalWidth || !img.naturalHeight) return;
			// Filter out tiny placeholder/spacer images (< 15px)
			if (img.naturalWidth < 15 || img.naturalHeight < 15) {
				setIsHidden(true);
				return;
			}

			// Offscreen canvas inspection to detect solid pitch-black or unicolor blocks
			const canvas = document.createElement("canvas");
			canvas.width = 16;
			canvas.height = 16;
			const ctx = canvas.getContext("2d", { willReadFrequently: true });
			if (!ctx) return;
			ctx.drawImage(img, 0, 0, 16, 16);
			const imgData = ctx.getImageData(0, 0, 16, 16).data;

			let visiblePixels = 0;
			let nonBlackPixels = 0;
			for (let i = 0; i < imgData.length; i += 4) {
				const r = imgData[i];
				const g = imgData[i + 1];
				const b = imgData[i + 2];
				const a = imgData[i + 3];
				// Only consider non-transparent pixels
				if (a > 25) {
					visiblePixels++;
					// If any visible pixel has non-black color (brightness above dark threshold 20)
					if (r > 20 || g > 20 || b > 20) {
						nonBlackPixels++;
					}
				}
			}

			// If image has visible pixels and all of them are pitch-black (r, g, b <= 20)
			if (visiblePixels > 0 && nonBlackPixels === 0) {
				setIsHidden(true);
			}
		} catch {
			// Fail open on CORS or canvas errors
		}
	};

	return (
		<>
			<span
				className={`${isCompact ? "my-1 w-28" : "my-2 w-64 sm:w-72"} flex flex-col max-w-full rounded-lg border border-zinc-200/80 bg-zinc-50/60 overflow-hidden shrink-0 relative group shadow-none`}
			>
				{/* Delete button (only shown when onDelete is provided, i.e. edit mode) */}
				{onDelete && (
					<button
						type="button"
						onClick={(e) => {
							e.stopPropagation();
							e.preventDefault();
							onDelete(strSrc, typeof alt === "string" ? alt : "");
						}}
						className="absolute top-1.5 right-1.5 z-10 p-0.5 rounded-full bg-red-600 text-white hover:bg-red-700 shadow-md cursor-pointer transition-colors"
						title="Hapus gambar ini"
					>
						<RiCloseLine className="size-4" />
					</button>
				)}
				<span
					className={`${isCompact ? "h-24 p-1" : "h-40 sm:h-44 p-2"} w-full flex items-center justify-center overflow-hidden relative cursor-pointer`}
					onClick={() => setIsOpen(true)}
				>
					{/* eslint-disable-next-line @next/next/no-img-element */}
					<img
						src={resolvedSrc}
						alt={altText}
						className="size-full object-contain block"
						loading="lazy"
						crossOrigin="anonymous"
						onLoad={handleImageLoad}
						onError={() => {
							setIsHidden(true);
						}}
						{...props}
					/>
					<button
						type="button"
						onClick={(e) => {
							e.stopPropagation();
							setIsOpen(true);
						}}
						className="absolute bottom-1.5 right-1.5 p-1 rounded-md bg-white/95 text-zinc-600 border border-zinc-200/80 opacity-0 group-hover:opacity-100 transition-opacity shadow-xs cursor-pointer"
						title="Zoom image"
					>
						<RiZoomInLine className="size-3.5" />
					</button>
				</span>
				{alt && typeof alt === "string" && (
					<span
						className={`block ${isCompact ? "px-1.5 py-1 text-[11px]" : "px-2.5 py-1.5 text-xs"} text-zinc-700 font-medium bg-white border-t border-zinc-200/70 truncate w-full text-center`}
						title={alt}
					>
						{alt}
					</span>
				)}
			</span>

			<ImagePreviewDialog
				src={resolvedSrc}
				alt={altText}
				isOpen={isOpen}
				onOpenChange={setIsOpen}
			/>
		</>
	);
}

/**
 * Recursively resolves \u241E sentinels and raw <br> tags into JSX <br /> elements.
 */
export function renderWithBreaks(children: React.ReactNode): React.ReactNode {
	if (typeof children === "string") {
		if (
			!children.includes("\u241E") &&
			!/<br\s*\/?>/i.test(children) &&
			!/&lt;br\s*\/?&gt;/i.test(children)
		) {
			return children;
		}
		const parts = children.split(/(?:\u241E|<br\s*\/?>|&lt;br\s*\/?&gt;)/gi);
		return parts.map((part, idx) => (
			<React.Fragment key={idx}>
				{idx > 0 && <br />}
				{part}
			</React.Fragment>
		));
	}
	if (Array.isArray(children)) {
		return children.map((child, idx) => (
			<React.Fragment key={idx}>{renderWithBreaks(child)}</React.Fragment>
		));
	}
	if (React.isValidElement(children) && (children.props as any)?.children) {
		const newChildren = renderWithBreaks((children.props as any).children);
		return React.cloneElement(children, undefined, newChildren);
	}
	return children;
}

export const defaultMarkdownComponents: Components = {
	img: MarkdownImage,
	blockquote: ({ children }) => {
		const textContent = extractNodeText(children).trim();

		const isDanger = /kontraindikasi|danger|forbid|bahaya/i.test(textContent);
		const isWarning = /perhatian|warning|caution|hati-hati|peringatan/i.test(textContent);
		const isSuccess = /success|rekomendasi|anjuran/i.test(textContent);

		let borderClass = "border-l-2 border-blue-600 bg-blue-50/40 text-zinc-900";

		if (isDanger) {
			borderClass = "border-l-2 border-red-600 bg-red-50/50 text-red-950";
		} else if (isWarning) {
			borderClass = "border-l-2 border-amber-600 bg-amber-50/50 text-amber-950";
		} else if (isSuccess) {
			borderClass = "border-l-2 border-emerald-600 bg-emerald-50/50 text-emerald-950";
		}

		return (
			<div
				className={`my-1.5 py-1.5 px-3 rounded-r-md ${borderClass} text-xs sm:text-sm leading-normal shadow-none [&>p]:m-0`}
			>
				{renderWithBreaks(children)}
			</div>
		);
	},
	p: ({ children }) => {
		const text = extractNodeText(children).trim();
		const isFAQMatch = text.match(/^\*\*Q:\s*([^*]+)\*\*\s*(?:\n+|:)?\s*(?:\*\*A:\s*)?(.+)$/i);
		if (isFAQMatch) {
			const question = isFAQMatch[1].trim();
			const answer = isFAQMatch[2].trim();
			return (
				<details className="my-2 p-2.5 rounded-md border border-zinc-200 bg-white group [&_summary::-webkit-details-marker]:hidden">
					<summary className="cursor-pointer text-sm font-medium text-zinc-900 flex items-center justify-between gap-2 list-none select-none">
						<span className="flex items-center gap-2">
							<span className="text-xs font-semibold text-zinc-700 bg-zinc-100 px-1.5 py-0.5 rounded border border-zinc-200">
								Q
							</span>
							<span>{renderWithBreaks(question)}</span>
						</span>
						<span className="text-zinc-400 text-xs font-mono transition-transform group-open:rotate-180">
							▾
						</span>
					</summary>
					<div className="pt-2 pl-7 text-xs sm:text-sm text-zinc-700 leading-normal border-t border-zinc-100 mt-2">
						{renderWithBreaks(answer)}
					</div>
				</details>
			);
		}
		return <p className="my-1 text-sm text-zinc-900 leading-normal font-normal">{renderWithBreaks(children)}</p>;
	},
	ol: ({ children, start, node: _node, ...props }: React.ComponentProps<"ol"> & { node?: unknown }) => (
		<ol
			start={start}
			className="list-decimal pl-5 my-1 space-y-0.5 text-sm text-zinc-900 leading-normal font-normal marker:text-zinc-600"
			{...props}
		>
			{children}
		</ol>
	),
	ul: ({ children, node: _node, ...props }: React.ComponentProps<"ul"> & { node?: unknown }) => (
		<ul
			className="list-disc pl-5 my-1 space-y-0.5 text-sm text-zinc-900 leading-normal font-normal marker:text-zinc-500"
			{...props}
		>
			{children}
		</ul >
	),
	li: ({ children, node: _node, ...props }: React.ComponentProps<"li"> & { node?: unknown }) => (
		<li className="text-sm leading-normal text-zinc-900 font-normal" {...props}>
			{renderWithBreaks(children)}
		</li>
	),
	h1: ({ children }) => (
		<h1 className="text-base font-semibold text-zinc-950 first:mt-1 mt-4 mb-2 tracking-tight">
			{renderWithBreaks(children)}
		</h1>
	),
	h2: ({ children }) => (
		<h2 className="text-sm sm:text-base font-semibold text-zinc-950 first:mt-1 mt-4 mb-1.5 flex items-center gap-2 tracking-tight">
			{renderWithBreaks(children)}
		</h2>
	),
	h3: ({ children }) => {
		const text = extractNodeText(children).trim();
		const isContra = /kontraindikasi/i.test(text);
		const isPreCare = /pre-care|persiapan/i.test(text);
		const isAfterCare = /aftercare|setelah/i.test(text);

		return (
			<h3
				className={`text-sm font-semibold mt-2.5 mb-1 flex items-center gap-1.5 ${
					isContra
						? "text-red-900"
						: isPreCare
							? "text-blue-900"
							: isAfterCare
								? "text-emerald-900"
								: "text-zinc-900"
				}`}
			>
				{renderWithBreaks(children)}
			</h3>
		);
	},
	strong: ({ children }) => <strong className="font-semibold text-zinc-950">{renderWithBreaks(children)}</strong>,
	hr: () => <div className="my-2 border-t border-zinc-100" />,
	table: (props) => <MarkdownTable {...props} />,
	thead: ({ children }) => (
		<thead className="bg-zinc-50 text-zinc-900 font-semibold">{children}</thead>
	),
	tbody: (props) => <MarkdownTbody {...props} />,
	tr: ({ children }) => <tr className="hover:bg-zinc-50/60 transition-colors">{children}</tr>,
	th: ({ children }) => <th className="px-3 py-1.5 font-semibold text-zinc-900 whitespace-nowrap min-w-[90px]">{renderWithBreaks(children)}</th>,
	td: ({ children }) => (
		<td className="px-3 py-1.5 text-zinc-800 font-normal min-w-[110px] break-normal align-top">
			<CompactImageContext.Provider value={true}>{renderWithBreaks(children)}</CompactImageContext.Provider>
		</td>
	),
	code: ({ children, className }) => {
		const isInline = !className || !className.includes("language-");
		if (isInline) {
			return (
				<code className="px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-800 font-mono text-xs border border-zinc-200/80">
					{children}
				</code>
			);
		}
		return <code className={className}>{children}</code>;
	},
	pre: ({ children }) => (
		<pre className="my-2 p-3 rounded-lg bg-zinc-900 text-zinc-100 text-xs font-mono overflow-x-auto">
			{children}
		</pre>
	),
};

/**
 * Creates markdown components with image delete support for edit mode.
 * Pass an onDeleteImage callback and each rendered image will show a red 'x' button.
 */
export function createEditableMarkdownComponents(
	onDeleteImage: (src: string, alt: string) => void
): Components {
	return {
		...defaultMarkdownComponents,
		img: (imgProps: React.ComponentProps<"img">) => (
			<MarkdownImage {...imgProps} onDelete={onDeleteImage} />
		),
	};
}

// Any inline markdown token: image, link, bold/italic, inline code, strikethrough
const INLINE_MARKDOWN_RE = /!\[|\]\(|\*\*|__|(^|[\s(])[*_][^\s*_]|`|~~/;

/**
 * Strips inline markdown from a table cell for plain-text search and sorting
 * (`![alt](url)` -> `alt`, `**x**` -> `x`).
 */
export function cellPlainText(cell: string): string {
	return cell
		.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
		.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
		.replace(/[*_`~]/g, "")
		.replace(/␞/g, " ");
}

/**
 * Renders a single table cell's inline markdown (images, bold, links) with the same
 * components as body content. Plain-text cells skip the markdown parser so large
 * tables stay fast.
 */
export function MarkdownTableCell({
	content,
	onDeleteImage,
}: {
	content: string;
	onDeleteImage?: (src: string, alt: string) => void;
}) {
	if (!INLINE_MARKDOWN_RE.test(content)) {
		return <>{renderWithBreaks(content)}</>;
	}
	const base = onDeleteImage ? createEditableMarkdownComponents(onDeleteImage) : defaultMarkdownComponents;
	const cellComponents: Components = {
		...base,
		// A cell is inline context: never emit block <p> margins
		p: ({ children }) => <span className="block">{renderWithBreaks(children)}</span>,
	};
	return (
		<CompactImageContext.Provider value={true}>
			<ReactMarkdown remarkPlugins={[remarkGfm]} components={cellComponents}>
				{content}
			</ReactMarkdown>
		</CompactImageContext.Provider>
	);
}
