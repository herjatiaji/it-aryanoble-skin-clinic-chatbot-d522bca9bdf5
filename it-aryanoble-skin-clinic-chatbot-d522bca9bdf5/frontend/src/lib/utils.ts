import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export function formatErrorDetail(detail: string): string {
	if (!detail) return detail;

	// Handle published duplicate document error
	if (detail.includes("sudah terpublikasi") || detail.includes("already published")) {
		const match = detail.match(/'([^']+)'/);
		const fileName = match ? match[1] : null;
		if (fileName) {
			return `Document '${fileName}' is already published in the active Knowledge Base. Use 'Edit Knowledge' to update it.`;
		}
		return "This document is already published in the active Knowledge Base. Use 'Edit Knowledge' to update it.";
	}

	// Handle draft duplicate in review queue error
	if (detail.includes("Draft peninjauan") || detail.includes("antrean On Review")) {
		const match = detail.match(/'([^']+)'/);
		const fileName = match ? match[1] : null;
		if (fileName) {
			return `A review draft for '${fileName}' already exists in On Review (Pending). Please review or delete the existing draft first.`;
		}
		return "A review draft for this document already exists in On Review (Pending).";
	}

	return detail;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getErrorMessage(error: any, defaultMessage = "An error occurred. Please try again."): string {
	if (!error) return defaultMessage;

	if (error.response?.status === 413 || error.status === 413) {
		const detail = error.response?.data?.detail;
		if (typeof detail === "string") {
			return formatErrorDetail(detail);
		}
		return "Ukuran file terlalu besar (melebihi batas maksimal 500 MB). Silakan perkecil ukuran file atau hubungi administrator.";
	}

	const detail = error.response?.data?.detail;

	if (typeof detail === "string") {
		return formatErrorDetail(detail);
	}

	if (Array.isArray(detail) && detail.length > 0 && detail[0].msg) {
		return formatErrorDetail(detail[0].msg);
	}

	return formatErrorDetail(error.message || defaultMessage);
}

export function stripMarkdown(markdown?: string | null): string {
	if (!markdown) return "";
	return markdown
		// Remove code blocks
		.replace(/```[\s\S]*?```/g, "")
		// Remove inline code
		.replace(/`([^`]+)`/g, "$1")
		// Remove images
		.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
		// Remove links, keep text
		.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
		// Remove headers (# Header)
		.replace(/^#{1,6}\s+/gm, "")
		.replace(/#{1,6}\s+/g, "")
		// Remove bold/italic (***text***, **text**, *text*, ___text___, __text__, _text_)
		.replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, "$1")
		// Remove strikethrough (~~text~~)
		.replace(/~~([^~]+)~~/g, "$1")
		// Remove blockquotes (> quote)
		.replace(/^>\s+/gm, "")
		// Remove list bullets (- item, * item, + item, 1. item)
		.replace(/^(\s*[-*+]\s+|\s*\d+\.\s+)/gm, "")
		// Remove table delimiters and pipes (| col1 | col2 | or |---|---|)
		.replace(/\|[-:\s|]+\|/g, " ")
		.replace(/\|/g, " ")
		// Remove horizontal rules (---, ***, ___)
		.replace(/^[-*_]{3,}\s*$/gm, "")
		// Replace multiple newlines or tabs with a single space
		.replace(/[\r\n\t]+/g, " ")
		// Replace multiple spaces with a single space
		.replace(/\s{2,}/g, " ")
		.trim();
}
