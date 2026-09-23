"use client";

import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
	RiArrowDownSLine,
	RiArrowGoBackLine,
	RiArrowGoForwardLine,
	RiBold,
	RiCodeBoxLine,
	RiCodeLine,
	RiDeleteBin7Line,
	RiDoubleQuotesL,
	RiInsertColumnLeft,
	RiInsertColumnRight,
	RiInsertRowBottom,
	RiInsertRowTop,
	RiItalic,
	RiListOrdered,
	RiListUnordered,
	RiSeparator,
	RiStrikethrough,
	RiTableLine,
} from "@remixicon/react";
import type { Editor } from "@tiptap/react";

interface EditorToolbarProps {
	editor: Editor | null;
}

export function EditorToolbar({ editor }: EditorToolbarProps) {
	if (!editor) {
		return null;
	}

	const getCurrentHeading = () => {
		if (editor.isActive("heading", { level: 1 })) return "Heading 1";
		if (editor.isActive("heading", { level: 2 })) return "Heading 2";
		if (editor.isActive("heading", { level: 3 })) return "Heading 3";
		return "Normal Text";
	};

	return (
		<div className="flex flex-wrap items-center gap-1 p-2 bg-zinc-50 border-b border-zinc-200">
			{/* Headings Selector */}
			<DropdownMenu>
				<DropdownMenuTrigger
					render={
						<Button
							type="button"
							variant="ghost"
							size="sm"
							className="h-8 px-2.5 text-xs font-medium text-zinc-700 bg-white hover:bg-zinc-100 border border-zinc-200 rounded-lg shadow-none gap-1.5 cursor-pointer"
						/>
					}
				>
					<span>{getCurrentHeading()}</span>
					<RiArrowDownSLine className="size-3.5 text-zinc-400" />
				</DropdownMenuTrigger>
				<DropdownMenuContent
					align="start"
					className="w-36 bg-white border border-zinc-200 rounded-lg shadow-none p-1"
				>
					<DropdownMenuItem
						onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().setParagraph().run()}
						className={`text-xs cursor-pointer rounded-md ${editor.isActive("paragraph") ? "font-semibold bg-zinc-100" : ""}`}
					>
						Normal Text
					</DropdownMenuItem>
					<DropdownMenuItem
						onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
						className={`text-xs cursor-pointer font-bold rounded-md ${editor.isActive("heading", { level: 1 }) ? "bg-zinc-100" : ""}`}
					>
						Heading 1
					</DropdownMenuItem>
					<DropdownMenuItem
						onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
						className={`text-xs cursor-pointer font-semibold rounded-md ${editor.isActive("heading", { level: 2 }) ? "bg-zinc-100" : ""}`}
					>
						Heading 2
					</DropdownMenuItem>
					<DropdownMenuItem
						onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
						className={`text-xs cursor-pointer font-medium rounded-md ${editor.isActive("heading", { level: 3 }) ? "bg-zinc-100" : ""}`}
					>
						Heading 3
					</DropdownMenuItem>
				</DropdownMenuContent>
			</DropdownMenu>

			<div className="h-4 w-px bg-zinc-300 mx-1" />

			{/* Inline Text Formatting */}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleBold().run()}
				title="Bold (Ctrl+B)"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("bold")
						? "bg-zinc-200 text-zinc-950 font-bold"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiBold className="size-4" />
			</Button>

			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleItalic().run()}
				title="Italic (Ctrl+I)"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("italic")
						? "bg-zinc-200 text-zinc-950"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiItalic className="size-4" />
			</Button>

			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleStrike().run()}
				title="Strikethrough"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("strike")
						? "bg-zinc-200 text-zinc-950"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiStrikethrough className="size-4" />
			</Button>

			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleCode().run()}
				title="Inline Code"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("code")
						? "bg-zinc-200 text-zinc-950"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiCodeLine className="size-4" />
			</Button>

			<div className="h-4 w-px bg-zinc-300 mx-1" />

			{/* Lists */}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleBulletList().run()}
				title="Bullet List"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("bulletList")
						? "bg-zinc-200 text-zinc-950"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiListUnordered className="size-4" />
			</Button>

			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleOrderedList().run()}
				title="Numbered List"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("orderedList")
						? "bg-zinc-200 text-zinc-950"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiListOrdered className="size-4" />
			</Button>

			<div className="h-4 w-px bg-zinc-300 mx-1" />

			{/* Blocks */}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleBlockquote().run()}
				title="Quote"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("blockquote")
						? "bg-zinc-200 text-zinc-950"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiDoubleQuotesL className="size-4" />
			</Button>

			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().toggleCodeBlock().run()}
				title="Code Block"
				className={`size-8 rounded-lg shadow-none cursor-pointer ${
					editor.isActive("codeBlock")
						? "bg-zinc-200 text-zinc-950"
						: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
				}`}
			>
				<RiCodeBoxLine className="size-4" />
			</Button>

			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().setHorizontalRule().run()}
				title="Divider"
				className="size-8 rounded-lg shadow-none cursor-pointer text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
			>
				<RiSeparator className="size-4" />
			</Button>

			<div className="h-4 w-px bg-zinc-300 mx-1" />

			{/* Table Controls */}
			<DropdownMenu>
				<DropdownMenuTrigger
					render={
						<Button
							type="button"
							variant="ghost"
							size="sm"
							className={`h-8 px-2.5 text-xs font-medium rounded-lg shadow-none gap-1 cursor-pointer ${
								editor.isActive("table")
									? "bg-zinc-200 text-zinc-950"
									: "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
							}`}
						/>
					}
				>
					<RiTableLine className="size-4" />
					<span className="hidden sm:inline">Table</span>
					<RiArrowDownSLine className="size-3.5 text-zinc-400" />
				</DropdownMenuTrigger>
				<DropdownMenuContent
					align="start"
					className="w-48 bg-white border border-zinc-200 rounded-lg shadow-none p-1"
				>
					{!editor.isActive("table") ? (
						<DropdownMenuItem
							onClick={() =>
								editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
							}
							className="text-xs cursor-pointer gap-2 rounded-md"
						>
							<RiTableLine className="size-3.5 text-zinc-500" />
							Insert 3x3 Table
						</DropdownMenuItem>
					) : (
						<>
							<DropdownMenuItem
								onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().addRowBefore().run()}
								className="text-xs cursor-pointer gap-2 rounded-md"
							>
								<RiInsertRowTop className="size-3.5 text-zinc-500" />
								Add Row Above
							</DropdownMenuItem>
							<DropdownMenuItem
								onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().addRowAfter().run()}
								className="text-xs cursor-pointer gap-2 rounded-md"
							>
								<RiInsertRowBottom className="size-3.5 text-zinc-500" />
								Add Row Below
							</DropdownMenuItem>
							<DropdownMenuItem
								onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().addColumnBefore().run()}
								className="text-xs cursor-pointer gap-2 rounded-md"
							>
								<RiInsertColumnLeft className="size-3.5 text-zinc-500" />
								Add Column Left
							</DropdownMenuItem>
							<DropdownMenuItem
								onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().addColumnAfter().run()}
								className="text-xs cursor-pointer gap-2 rounded-md"
							>
								<RiInsertColumnRight className="size-3.5 text-zinc-500" />
								Add Column Right
							</DropdownMenuItem>
							<DropdownMenuSeparator />
							<DropdownMenuItem
								onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().deleteRow().run()}
								className="text-xs cursor-pointer gap-2 text-red-600 rounded-md"
							>
								<RiDeleteBin7Line className="size-3.5 text-red-500" />
								Delete Current Row
							</DropdownMenuItem>
							<DropdownMenuItem
								onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().deleteColumn().run()}
								className="text-xs cursor-pointer gap-2 text-red-600 rounded-md"
							>
								<RiDeleteBin7Line className="size-3.5 text-red-500" />
								Delete Current Column
							</DropdownMenuItem>
							<DropdownMenuItem
								onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().deleteTable().run()}
								className="text-xs cursor-pointer gap-2 text-red-600 font-medium rounded-md"
							>
								<RiDeleteBin7Line className="size-3.5 text-red-500" />
								Delete Table
							</DropdownMenuItem>
						</>
					)}
				</DropdownMenuContent>
			</DropdownMenu>

			<div className="flex-1" />

			{/* Undo / Redo */}
			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().undo().run()}
				disabled={!editor.can().undo()}
				title="Undo (Ctrl+Z)"
				className="size-8 rounded-lg shadow-none cursor-pointer text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 disabled:opacity-40"
			>
				<RiArrowGoBackLine className="size-4" />
			</Button>

			<Button
				type="button"
				variant="ghost"
				size="icon"
				onMouseDown={(e) => e.preventDefault()}
							onClick={() => editor.chain().focus().redo().run()}
				disabled={!editor.can().redo()}
				title="Redo (Ctrl+Shift+Z)"
				className="size-8 rounded-lg shadow-none cursor-pointer text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 disabled:opacity-40"
			>
				<RiArrowGoForwardLine className="size-4" />
			</Button>
		</div>
	);
}
