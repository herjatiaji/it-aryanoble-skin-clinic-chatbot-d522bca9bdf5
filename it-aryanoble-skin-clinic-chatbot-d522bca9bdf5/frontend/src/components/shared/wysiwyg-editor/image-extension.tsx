"use client";

import { resolveImageUrl } from "@/components/shared/markdown/utils";
import {
	RiCheckLine,
	RiCloseLine,
	RiDeleteBin7Line,
	RiEdit2Line,
	RiImageLine,
} from "@remixicon/react";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import {
	mergeAttributes,
	Node,
	NodeViewWrapper,
	ReactNodeViewRenderer,
	type NodeViewProps,
} from "@tiptap/react";
import React, { useState } from "react";

interface MarkdownSerializerState {
	write: (text: string) => void;
	esc: (text: string) => string;
}

function EditorImageComponent({ node, updateAttributes, deleteNode, selected }: NodeViewProps) {
	const rawSrc = (node.attrs.src as string) || "";
	const alt = (node.attrs.alt as string) || "";
	const [isEditingLabel, setIsEditingLabel] = useState(false);
	const [tempLabel, setTempLabel] = useState(alt);
	const [hasError, setHasError] = useState(false);

	const resolvedSrc = resolveImageUrl(rawSrc);

	const handleSaveLabel = (e?: React.FormEvent | React.MouseEvent) => {
		if (e) {
			e.preventDefault();
			e.stopPropagation();
		}
		const clean = tempLabel.trim();
		updateAttributes({ alt: clean });
		setIsEditingLabel(false);
	};

	const handleCancelLabel = (e?: React.MouseEvent) => {
		if (e) {
			e.preventDefault();
			e.stopPropagation();
		}
		setTempLabel(alt);
		setIsEditingLabel(false);
	};

	return (
		<NodeViewWrapper
			as="span"
			className={`inline-flex flex-col items-center my-1.5 mx-1 align-middle select-none max-w-56 group/img ${
				selected ? "ring-2 ring-blue-500 rounded-lg" : ""
			}`}
		>
			<span className="relative flex flex-col items-center bg-white border border-zinc-200 hover:border-blue-400 rounded-lg p-1.5 shadow-2xs hover:shadow-xs transition-all w-full">
				{/* Image Thumbnail */}
				{hasError || !resolvedSrc ? (
					<span className="flex flex-col items-center justify-center w-28 h-20 bg-zinc-100 rounded text-zinc-400 text-xs">
						<RiImageLine className="size-6 text-zinc-400 mb-1" />
						<span className="text-[10px]">Gambar tidak tersedia</span>
					</span>
				) : (
					/* eslint-disable-next-line @next/next/no-img-element */
					<img
						src={resolvedSrc}
						alt={alt || "Gambar dokumen"}
						onError={() => setHasError(true)}
						className="max-h-24 max-w-48 object-contain rounded bg-zinc-50 border border-zinc-100"
						loading="lazy"
					/>
				)}

				{/* Label / Caption or Inline Edit Input */}
				{isEditingLabel ? (
					<span className="flex items-center gap-1 mt-1.5 w-full" onClick={(e) => e.stopPropagation()}>
						<input
							type="text"
							value={tempLabel}
							onChange={(e) => setTempLabel(e.target.value)}
							onKeyDown={(e) => {
								if (e.key === "Enter") handleSaveLabel(e);
								if (e.key === "Escape") handleCancelLabel(e as unknown as React.MouseEvent);
							}}
							placeholder="Label gambar..."
							className="text-[11px] px-1.5 py-0.5 border border-blue-400 rounded bg-white text-zinc-900 focus:outline-none w-full min-w-0"
							autoFocus
						/>
						<button
							type="button"
							onClick={handleSaveLabel}
							className="p-1 rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer shrink-0"
							title="Simpan Label (Enter)"
						>
							<RiCheckLine className="size-3" />
						</button>
						<button
							type="button"
							onClick={handleCancelLabel}
							className="p-1 rounded bg-zinc-200 text-zinc-600 hover:bg-zinc-300 cursor-pointer shrink-0"
							title="Batal (Esc)"
						>
							<RiCloseLine className="size-3" />
						</button>
					</span>
				) : (
					<span className="flex items-center justify-between gap-1 mt-1 w-full px-0.5">
						<span
							className="text-[10px] font-medium text-zinc-600 truncate max-w-36"
							title={alt || "Klik icon pensil untuk edit label"}
						>
							{alt || "Tanpa label"}
						</span>
						<span className="flex items-center gap-0.5 opacity-0 group-hover/img:opacity-100 transition-opacity">
							<button
								type="button"
								onClick={(e) => {
									e.preventDefault();
									e.stopPropagation();
									setTempLabel(alt);
									setIsEditingLabel(true);
								}}
								className="p-0.5 text-zinc-400 hover:text-blue-600 rounded cursor-pointer"
								title="Edit label gambar"
							>
								<RiEdit2Line className="size-3" />
							</button>
							<button
								type="button"
								onClick={(e) => {
									e.preventDefault();
									e.stopPropagation();
									deleteNode();
								}}
								className="p-0.5 text-zinc-400 hover:text-red-600 rounded cursor-pointer"
								title="Hapus gambar"
							>
								<RiDeleteBin7Line className="size-3" />
							</button>
						</span>
					</span>
				)}
			</span>
		</NodeViewWrapper>
	);
}

export const EditorImage = Node.create({
	name: "image",
	group: "inline",
	inline: true,
	draggable: true,
	selectable: true,
	atom: true,

	addAttributes() {
		return {
			src: { default: null },
			alt: { default: null },
			title: { default: null },
		};
	},

	parseHTML() {
		return [
			{
				tag: "img[src]",
				getAttrs: (dom) => {
					if (!(dom instanceof HTMLElement)) return false;
					let src = dom.getAttribute("src") || "";
					const backendBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(
						/\/api\/?$/,
						"",
					);
					if (src.startsWith(backendBase)) {
						src = src.slice(backendBase.length);
					}
					return {
						src,
						alt: dom.getAttribute("alt") || null,
						title: dom.getAttribute("title") || null,
					};
				},
			},
		];
	},

	renderHTML({ HTMLAttributes }) {
		const rawSrc = (HTMLAttributes.src as string) || "";
		const resolved = resolveImageUrl(rawSrc);
		return [
			"img",
			mergeAttributes(HTMLAttributes, {
				src: resolved,
				class: "editor-image inline-block max-h-24 max-w-48 rounded border border-zinc-200 bg-white object-contain p-1 shadow-2xs align-middle",
			}),
		];
	},

	addNodeView() {
		return ReactNodeViewRenderer(EditorImageComponent);
	},

	addStorage() {
		return {
			markdown: {
				serialize(state: MarkdownSerializerState, node: ProseMirrorNode) {
					const alt = state.esc((node.attrs.alt as string) || "");
					let src = (node.attrs.src as string) || "";
					const backendBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(
						/\/api\/?$/,
						"",
					);
					if (src.startsWith(backendBase)) {
						src = src.slice(backendBase.length);
					}
					const title = node.attrs.title ? ` "${String(node.attrs.title).replace(/"/g, '\\"')}"` : "";
					state.write(`![${alt}](${src}${title})`);
				},
				parse: {
					/**
					 * Ensure <img> inside <td>/<th> is wrapped in <p> so ProseMirror's
					 * tableCell (content: block+) can accept it during DOM parsing.
					 * markdown-it renders `![alt](url)` inside table cells as bare <img>
					 * without a <p> wrapper, which causes ProseMirror to silently drop
					 * the inline image node.
					 */
					updateDOM(element: HTMLElement) {
						element.querySelectorAll("td > img, th > img").forEach((img) => {
							const p = element.ownerDocument.createElement("p");
							img.parentNode?.insertBefore(p, img);
							p.appendChild(img);
						});
					},
				},
			},
		};
	},
});
