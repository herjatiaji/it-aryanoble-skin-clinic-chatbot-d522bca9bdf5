import * as React from "react";
import { validateAndFilterFiles } from "../utils/prompt-input-utils";

interface UsePromptAttachmentsProps {
	disabled?: boolean;
}

export function usePromptAttachments({ disabled }: UsePromptAttachmentsProps = {}) {
	const [attachedFiles, setAttachedFiles] = React.useState<File[]>([]);
	const [isDragging, setIsDragging] = React.useState(false);
	const dragCounter = React.useRef(0);

	const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		const files = e.target.files;
		if (files && files.length > 0) {
			const filtered = validateAndFilterFiles(Array.from(files));
			if (filtered.length > 0) {
				setAttachedFiles((prev) => [...prev, ...filtered]);
			}
		}
	};

	const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (disabled) return;

		if (e.dataTransfer.types && Array.from(e.dataTransfer.types).includes("Files")) {
			dragCounter.current += 1;
			setIsDragging(true);
		}
	};

	const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (disabled) return;

		dragCounter.current -= 1;
		if (dragCounter.current <= 0) {
			dragCounter.current = 0;
			setIsDragging(false);
		}
	};

	const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (disabled) return;

		if (e.dataTransfer) {
			e.dataTransfer.dropEffect = "copy";
		}
	};

	const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (disabled) return;

		dragCounter.current = 0;
		setIsDragging(false);

		if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
			const filtered = validateAndFilterFiles(Array.from(e.dataTransfer.files));
			if (filtered.length > 0) {
				setAttachedFiles((prev) => [...prev, ...filtered]);
			}
		}
	};

	const handlePaste = (e: React.ClipboardEvent) => {
		if (disabled) return;
		if (e.clipboardData.files && e.clipboardData.files.length > 0) {
			e.preventDefault();
			const filtered = validateAndFilterFiles(Array.from(e.clipboardData.files));
			if (filtered.length > 0) {
				setAttachedFiles((prev) => [...prev, ...filtered]);
			}
		}
	};

	const removeFile = (indexToRemove: number) => {
		setAttachedFiles((prev) => prev.filter((_, index) => index !== indexToRemove));
	};

	const clearAttachedFiles = () => {
		setAttachedFiles([]);
	};

	return {
		attachedFiles,
		setAttachedFiles,
		isDragging,
		handleFileChange,
		handleDragEnter,
		handleDragLeave,
		handleDragOver,
		handleDrop,
		handlePaste,
		removeFile,
		clearAttachedFiles,
	};
}
