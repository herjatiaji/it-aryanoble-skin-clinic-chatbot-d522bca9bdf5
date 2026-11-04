"use client";

import { Button } from "@/components/ui/button";
import {
	RiCheckLine,
	RiCloseLine,
	RiEdit2Line,
	RiLoader4Line,
} from "@remixicon/react";
import { Placeholder } from "@tiptap/extension-placeholder";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import { TableRow } from "@tiptap/extension-table-row";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import React, { useCallback, useEffect, useRef } from "react";
import { Markdown } from "tiptap-markdown";
import { EditorToolbar } from "./editor-toolbar";
import { EditorImage } from "./image-extension";
import { CustomTable } from "./table-extension";

interface WysiwygEditorProps {
	initialContent: string;
	onSave: (markdown: string) => void | Promise<void>;
	onCancel: () => void;
	onChange?: (markdown: string) => void;
	isSaving?: boolean;
	autoFocus?: boolean;
}

export function WysiwygEditor(props: WysiwygEditorProps) {
	if ((props.initialContent || "").length > 50000) {
		return <LargeDocumentRawEditor {...props} />;
	}
	return <TiptapRichEditor {...props} />;
}

function LargeDocumentRawEditor({
	initialContent,
	onSave,
	onCancel,
	onChange,
	isSaving = false,
}: WysiwygEditorProps) {
	const [value, setValue] = React.useState(initialContent || "");
	const [forceRichText, setForceRichText] = React.useState(false);

	const prevInitialRef = React.useRef(initialContent);
	React.useEffect(() => {
		if (initialContent !== prevInitialRef.current) {
			prevInitialRef.current = initialContent;
			setValue(initialContent || "");
		}
	}, [initialContent]);

	if (forceRichText) {
		return (
			<TiptapRichEditor
				initialContent={value}
				onSave={onSave}
				onCancel={onCancel}
				onChange={onChange}
				isSaving={isSaving}
			/>
		);
	}

	const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
		const val = e.target.value;
		setValue(val);
		onChange?.(val);
	};

	const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
		if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
			e.preventDefault();
			onSave(value);
		} else if (e.key === "Escape") {
			e.preventDefault();
			onCancel();
		}
	};

	return (
		<div className="flex flex-col w-full bg-white rounded-lg border border-zinc-200 shadow-none overflow-hidden transition-all">
			<div className="flex items-center justify-between px-4 py-2.5 bg-amber-50/70 border-b border-amber-200/80 rounded-t-lg">
				<div className="flex items-center gap-2 text-xs font-semibold text-amber-950">
					<RiEdit2Line className="size-4 text-amber-600" />
					<span>High-Performance Text Editor</span>
					<span className="text-[11px] font-normal text-amber-800 bg-amber-100/80 border border-amber-200 px-2 py-0.5 rounded-full">
						Dokumen Sangat Besar ({Math.round((initialContent.length) / 1024)} KB / {initialContent.split("\n").length.toLocaleString("id-ID")} baris)
					</span>
				</div>

				<div className="flex items-center gap-2">
					<button
						type="button"
						onClick={() => setForceRichText(true)}
						className="text-[11px] text-zinc-500 hover:text-zinc-800 underline mr-2 cursor-pointer"
					>
						Beralih ke Visual Rich Text (mungkin lambat)
					</button>
					<Button
						type="button"
						size="sm"
						variant="outline"
						onClick={onCancel}
						disabled={isSaving}
						className="h-8 px-3 text-xs font-medium border border-zinc-200 text-zinc-700 bg-white hover:bg-zinc-100 rounded-lg shadow-none cursor-pointer"
					>
						<RiCloseLine className="size-3.5 mr-1" />
						Cancel
					</Button>
					<Button
						type="button"
						size="sm"
						variant="default"
						onClick={() => onSave(value)}
						disabled={isSaving}
						className="h-8 px-3.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-none cursor-pointer gap-1.5"
					>
						{isSaving ? (
							<>
								<RiLoader4Line className="size-3.5 animate-spin" />
								Saving...
							</>
						) : (
							<>
								<RiCheckLine className="size-3.5" />
								Save Changes
							</>
						)}
					</Button>
				</div>
			</div>

			<div className="p-3 bg-zinc-50 border-b border-zinc-200 text-xs text-zinc-600">
				💡 Dokumen ini memiliki ribuan baris data tabel. Menggunakan editor teks langsung mencegah browser membeku (freeze) dan memastikan penulisan tetap lancar.
			</div>

			<textarea
				value={value}
				onChange={handleChange}
				onKeyDown={handleKeyDown}
				className="w-full min-h-[500px] max-h-[70vh] p-4 font-mono text-xs text-zinc-900 bg-white focus:outline-none resize-y leading-relaxed"
				placeholder="Edit markdown content..."
				spellCheck={false}
			/>

			<div className="flex items-center justify-between px-4 py-2 bg-zinc-50/80 border-t border-zinc-200 rounded-b-lg text-[11px] text-zinc-500 shadow-none">
				<span>
					Mode Teks Berperforma Tinggi — Mendukung format Markdown langsung.
				</span>
				<div className="flex items-center gap-3">
					<span>
						Tekan <kbd className="px-1.5 py-0.5 bg-zinc-200/80 border border-zinc-300 rounded-md text-[10px] text-zinc-700 font-mono shadow-none">Ctrl+Enter</kbd> untuk simpan
					</span>
					<span>
						<kbd className="px-1.5 py-0.5 bg-zinc-200/80 border border-zinc-300 rounded-md text-[10px] text-zinc-700 font-mono shadow-none">Esc</kbd> untuk batal
					</span>
				</div>
			</div>
		</div>
	);
}

function TiptapRichEditor({
	initialContent,
	onSave,
	onCancel,
	onChange,
	isSaving = false,
}: WysiwygEditorProps) {
	// Guard: skip the first onUpdate call which fires on mount/content-set
	// to prevent serialized content (which may lose images) from overwriting
	// the parent's localSummary before the user has actually edited anything.
	const isFirstUpdate = useRef(true);

	const editor = useEditor({
		immediatelyRender: false,
		extensions: [
			StarterKit.configure({
				heading: {
					levels: [1, 2, 3],
				},
			}),
			CustomTable.configure({
				resizable: true,
				HTMLAttributes: {
					class: "border-collapse table-auto w-full my-3 border border-zinc-200",
				},
			}),
			TableRow.configure({
				HTMLAttributes: {
					class: "border-b border-zinc-200",
				},
			}),
			TableHeader.configure({
				HTMLAttributes: {
					class: "bg-zinc-100 font-semibold text-left p-2.5 border border-zinc-200 text-xs text-zinc-900",
				},
			}),
			TableCell.configure({
				HTMLAttributes: {
					class: "p-2.5 border border-zinc-200 text-xs text-zinc-800 align-top",
				},
			}),
			EditorImage,
			Placeholder.configure({
				placeholder: "Type your formatted knowledge content here...",
			}),
			Markdown.configure({
				html: true,
				tightLists: true,
				tightListClass: "tight",
				bulletListMarker: "-",
				linkify: true,
				breaks: false,
				transformPastedText: true,
				transformCopiedText: true,
			}),
		],
		content: initialContent || "",
		editorProps: {
			attributes: {
				class:
					"tiptap focus:outline-none min-h-75 p-4 text-zinc-900 text-sm leading-relaxed",
			},
		},
		onUpdate: ({ editor: ed }) => {
			// Skip the initial onUpdate that fires when content is first set.
			// This prevents the serialized markdown (which may drop images from
			// table cells) from overwriting the parent's localSummary before
			// the user has actually made any edits.
			if (isFirstUpdate.current) {
				isFirstUpdate.current = false;
				return;
			}
			const storage = ed.storage as unknown as Record<string, { getMarkdown?: () => string }>;
			const md = storage.markdown?.getMarkdown?.() || "";
			if (onChange) {
				onChange(md);
			}
		},
	});

	// Sync initial content if editor was mounted before async data resolved
	useEffect(() => {
		if (editor && initialContent && !editor.getText().trim()) {
			editor.commands.setContent(initialContent);
		}
	}, [editor, initialContent]);

	// Save trigger
	const handleSaveTrigger = useCallback(() => {
		if (editor) {
			const storage = editor.storage as unknown as Record<string, { getMarkdown?: () => string }>;
			const md = storage.markdown?.getMarkdown?.() || "";
			onSave(md);
		}
	}, [editor, onSave]);

	// Keyboard shortcuts (Ctrl+Enter to save, Esc to cancel)
	useEffect(() => {
		const handleKeyDown = (e: KeyboardEvent) => {
			if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
				e.preventDefault();
				handleSaveTrigger();
			} else if (e.key === "Escape") {
				e.preventDefault();
				onCancel();
			}
		};

		window.addEventListener("keydown", handleKeyDown);
		return () => window.removeEventListener("keydown", handleKeyDown);
	}, [handleSaveTrigger, onCancel]);

	return (
		<div className="flex flex-col w-full bg-white rounded-lg border border-zinc-200 shadow-none overflow-hidden transition-all">
			{/* Top Header Bar with Visual Editor Label and Action Buttons */}
			<div className="flex items-center justify-between px-4 py-2.5 bg-zinc-50 border-b border-zinc-200 rounded-t-lg">
				<div className="flex items-center gap-2 text-xs font-semibold text-zinc-800">
					<RiEdit2Line className="size-4 text-blue-600" />
					<span>Visual Editor</span>
				</div>

				{/* Save & Cancel Actions */}
				<div className="flex items-center gap-2">
					<Button
						type="button"
						size="sm"
						variant="outline"
						onClick={onCancel}
						disabled={isSaving}
						className="h-8 px-3 text-xs font-medium border border-zinc-200 text-zinc-700 bg-white hover:bg-zinc-100 rounded-lg shadow-none cursor-pointer"
					>
						<RiCloseLine className="size-3.5 mr-1" />
						Cancel
					</Button>
					<Button
						type="button"
						size="sm"
						variant="default"
						onClick={handleSaveTrigger}
						disabled={isSaving}
						className="h-8 px-3.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-none cursor-pointer gap-1.5"
					>
						{isSaving ? (
							<>
								<RiLoader4Line className="size-3.5 animate-spin" />
								Saving...
							</>
						) : (
							<>
								<RiCheckLine className="size-3.5" />
								Save Changes
							</>
						)}
					</Button>
				</div>
			</div>

			{/* Visual Formatting Toolbar */}
			<EditorToolbar editor={editor} />

			{/* Main Editor Body */}
			<div className="flex-1 min-h-75 max-h-137.5 overflow-y-auto bg-white custom-scrollbar">
				<EditorContent editor={editor} />
			</div>

			{/* Bottom Helper Footer */}
			<div className="flex items-center justify-between px-4 py-2 bg-zinc-50/80 border-t border-zinc-200 rounded-b-lg text-[11px] text-zinc-500 shadow-none">
				<span>
					Visual WYSIWYG Mode — Use toolbar or markdown shortcuts (<code className="px-1 py-0.5 rounded bg-zinc-200/70 font-mono text-[10px] text-zinc-700">-</code>, <code className="px-1 py-0.5 rounded bg-zinc-200/70 font-mono text-[10px] text-zinc-700">1.</code>, <code className="px-1 py-0.5 rounded bg-zinc-200/70 font-mono text-[10px] text-zinc-700">#</code>, <code className="px-1 py-0.5 rounded bg-zinc-200/70 font-mono text-[10px] text-zinc-700">&gt;</code>)
				</span>
				<div className="flex items-center gap-3">
					<span>
						Press{" "}
						<kbd className="px-1.5 py-0.5 bg-zinc-200/80 border border-zinc-300 rounded-md text-[10px] text-zinc-700 font-mono shadow-none">
							Ctrl+Enter
						</kbd>{" "}
						to save
					</span>
					<span>
						<kbd className="px-1.5 py-0.5 bg-zinc-200/80 border border-zinc-300 rounded-md text-[10px] text-zinc-700 font-mono shadow-none">
							Esc
						</kbd>{" "}
						to cancel
					</span>
				</div>
			</div>
		</div>
	);
}
