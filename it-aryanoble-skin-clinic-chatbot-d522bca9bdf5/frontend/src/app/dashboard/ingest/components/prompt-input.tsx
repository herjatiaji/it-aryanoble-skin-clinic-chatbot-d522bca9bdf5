"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
	RiAttachmentLine,
	RiCornerDownLeftLine,
	RiLoader4Line,
	RiUploadCloud2Line,
} from "@remixicon/react";
import * as React from "react";
import { usePromptAttachments } from "../hooks/use-prompt-attachments";
import { ACCEPT_STRING } from "../utils/prompt-input-utils";
import { PromptAttachmentList } from "./prompt-attachment-list";

export interface PromptInputProps extends React.HTMLAttributes<HTMLDivElement> {
	onSend?: (value: string, category: string | undefined, files: File[]) => boolean | void;
	value?: string;
	onValueChange?: (val: string) => void;
	showAttachButton?: boolean;
	showAttachText?: boolean;
	attachText?: string;
	defaultValue?: string;
	placeholder?: string;
	minRows?: number;
	disabled?: boolean;
	isLoading?: boolean;
	uploadProgress?: number;
	autoFocus?: boolean;
	enableGlobalSlashFocus?: boolean;
}

export function PromptInput({
	className,
	onSend,
	value,
	onValueChange,
	showAttachButton = true,
	showAttachText,
	attachText = "Add files",
	defaultValue = "",
	placeholder,
	minRows = 1,
	disabled,
	isLoading,
	uploadProgress,
	autoFocus,
	enableGlobalSlashFocus = true,
	...props
}: PromptInputProps) {
	const isControlled = value !== undefined;
	const [uncontrolledValue, setUncontrolledValue] = React.useState(defaultValue);
	const inputValue = isControlled ? value : uncontrolledValue;

	const {
		attachedFiles,
		isDragging,
		handleFileChange,
		handleDragEnter,
		handleDragLeave,
		handleDragOver,
		handleDrop,
		handlePaste,
		removeFile,
		clearAttachedFiles,
	} = usePromptAttachments({ disabled });

	const textareaRef = React.useRef<HTMLTextAreaElement>(null);

	const handleSend = () => {
		if (disabled || isLoading || (!inputValue.trim() && attachedFiles.length === 0)) return;
		const currentFiles = [...attachedFiles];
		const currentText = inputValue;
		const success = onSend?.(currentText, undefined, currentFiles);
		if (success !== false) {
			if (!isControlled) {
				setUncontrolledValue("");
			}
			onValueChange?.("");
			if (currentFiles.length === 0) {
				clearAttachedFiles();
			}
			if (textareaRef.current) {
				textareaRef.current.style.height = "auto";
			}
		}
	};

	const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
		if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
			e.preventDefault();
			handleSend();
		} else if (e.key === "Escape") {
			e.currentTarget.blur();
		}
	};

	React.useEffect(() => {
		if (!enableGlobalSlashFocus) return;
		const handleGlobalKeyDown = (e: KeyboardEvent) => {
			const target = e.target as HTMLElement | null;
			const isInputActive =
				target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
			if (e.key === "/" && !isInputActive && !disabled) {
				e.preventDefault();
				textareaRef.current?.focus();
			}
		};
		window.addEventListener("keydown", handleGlobalKeyDown);
		return () => window.removeEventListener("keydown", handleGlobalKeyDown);
	}, [disabled, enableGlobalSlashFocus]);

	return (
		<div
			className={cn(
				"relative w-full rounded-lg p-3 transition-all border",
				isDragging
					? "border-blue-500 bg-blue-50/50"
					: "border-zinc-200/80 bg-zinc-50/50 hover:border-zinc-300 focus-within:border-zinc-300 focus-within:bg-white",
				className,
			)}
			onDragEnter={handleDragEnter}
			onDragLeave={handleDragLeave}
			onDragOver={handleDragOver}
			onDrop={handleDrop}
			onPaste={handlePaste}
			{...props}
		>
			{/* Drag & Drop Visual Overlay */}
			{isDragging && (
				<div className="absolute inset-0 z-30 flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-blue-500 bg-blue-50/95 pointer-events-none gap-2 p-4 text-center">
					<div className="flex items-center justify-center size-10 rounded-full bg-blue-100 text-blue-600">
						<RiUploadCloud2Line className="size-5" />
					</div>
					<div className="flex flex-col items-center gap-0.5">
						<span className="text-xs font-semibold text-zinc-900">Drop files here to attach</span>
						<span className="text-[11px] text-zinc-500">Release to add files to your prompt</span>
					</div>
				</div>
			)}

			{/* Attached Files Preview with Interactive Progress Bar */}
			<PromptAttachmentList
				files={attachedFiles}
				isLoading={isLoading}
				uploadProgress={uploadProgress}
				onRemoveFile={removeFile}
			/>

			{/* Input Area */}
			<div className="mb-2">
				<textarea
					ref={textareaRef}
					rows={minRows}
					autoFocus={autoFocus}
					disabled={disabled}
					className="w-full bg-transparent resize-none outline-none border-none text-sm text-zinc-950 placeholder:text-zinc-500 overflow-y-auto max-h-32 custom-scrollbar disabled:opacity-50 disabled:cursor-not-allowed"
					placeholder={
						disabled
							? "AI Assistant access is disabled..."
							: placeholder || "Describe what you want to ingest or ask..."
					}
					value={inputValue}
					onKeyDown={handleKeyDown}
					onChange={(e) => {
						if (!isControlled) {
							setUncontrolledValue(e.target.value);
						}
						onValueChange?.(e.target.value);
						e.target.style.height = "auto";
						e.target.style.height = e.target.scrollHeight + "px";
					}}
				/>
			</div>

			{/* Actions Area */}
			<div className="flex items-center justify-between">
				<div className="flex items-center gap-1.5">
					{/* Attach Button */}
					{showAttachButton && (
						<label
							htmlFor={disabled ? undefined : "file-upload"}
							className={cn(
								"flex items-center justify-center rounded-md border border-border bg-white text-zinc-700 transition-colors",
								disabled
									? "opacity-50 cursor-not-allowed"
									: "cursor-pointer hover:border-blue-500 hover:bg-blue-50 hover:text-blue-700",
								showAttachText ? "py-1.5 px-2.5 gap-1.5" : "aspect-square p-1.5",
							)}
							title={disabled ? "Access disabled" : "Upload file"}
						>
							<input
								id="file-upload"
								type="file"
								accept={ACCEPT_STRING}
								disabled={disabled}
								className="sr-only"
								onChange={handleFileChange}
								onClick={(e) => {
									(e.target as HTMLInputElement).value = "";
								}}
								multiple
							/>
							<RiAttachmentLine className="size-4 pointer-events-none shrink-0" />
							{showAttachText && (
								<span className="text-xs font-medium pointer-events-none">{attachText}</span>
							)}
						</label>
					)}
				</div>

				{/* Send Button */}
				<Button
					size="icon"
					disabled={disabled || isLoading || (!inputValue.trim() && attachedFiles.length === 0)}
					title="Send (Enter) • New line (Shift+Enter)"
					className="size-8 bg-blue-600 hover:bg-blue-700 rounded-lg shrink-0 text-white disabled:opacity-50 shadow-none cursor-pointer"
					onClick={handleSend}
				>
					{isLoading ? (
						<RiLoader4Line className="size-4 animate-spin" />
					) : (
						<RiCornerDownLeftLine className="size-4" />
					)}
				</Button>
			</div>
		</div>
	);
}
