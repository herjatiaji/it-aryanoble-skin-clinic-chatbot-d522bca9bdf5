import React from "react";
import type { KeyValueItem } from "./types";

export function resolveImageUrl(src?: string | null): string {
	if (!src) return "";
	let trimmed = src.trim();

	// Normalize hallucinated `https://api/` or `http://api/` prefixes
	if (/^https?:\/\/api\//i.test(trimmed)) {
		trimmed = trimmed.replace(/^https?:\/\/api\//i, "/api/");
	}

	const backendBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(
		/\/api\/?$/,
		"",
	);

	// If URL contains an internal backend host (localhost, 127.0.0.1, minio) or storage path, normalize to relative path first
	const isInternalHost = /^(?:https?:\/\/)?(?:localhost|127\.0\.0\.1|minio)(?::\d+)?/i.test(trimmed);
	const hasStoragePath = trimmed.includes("/api/storage/") || trimmed.includes("/storage/");

	if (hasStoragePath || isInternalHost) {
		if (trimmed.includes("/api/storage/")) {
			trimmed = `/api/storage/${trimmed.split("/api/storage/").pop()?.replace(/^\//, "")}`;
		} else if (trimmed.includes("/storage/")) {
			trimmed = `/api/storage/${trimmed.split("/storage/").pop()?.replace(/^\//, "")}`;
		} else {
			trimmed = trimmed.replace(/^(?:https?:\/\/)?(?:[^\/]+)/, "");
		}
	} else if (
		trimmed.startsWith("http://") ||
		trimmed.startsWith("https://") ||
		trimmed.startsWith("data:") ||
		trimmed.startsWith("blob:")
	) {
		// External 3rd party URL (e.g. CDN or public media)
		return encodeURI(decodeURI(trimmed));
	}

	// Strip known MinIO bucket names if extracted from direct S3/MinIO paths
	trimmed = trimmed.replace(/^\/?(?:skin-clinic-chatbot-dev|knowledge-documents|staging|approved)\//i, "/");

	// Normalize storage / images paths to /api/storage/...
	let normalizedPath = trimmed;
	if (normalizedPath.startsWith("/api/storage/")) {
		// already standard /api/storage/...
	} else if (normalizedPath.startsWith("api/storage/")) {
		normalizedPath = `/${normalizedPath}`;
	} else if (normalizedPath.startsWith("/storage/")) {
		normalizedPath = `/api${normalizedPath}`;
	} else if (normalizedPath.startsWith("storage/")) {
		normalizedPath = `/api/${normalizedPath}`;
	} else if (normalizedPath.startsWith("/images/")) {
		normalizedPath = `/api/storage${normalizedPath}`;
	} else if (normalizedPath.startsWith("images/")) {
		normalizedPath = `/api/storage/${normalizedPath}`;
	} else {
		// Bare filename or clean key without prefix e.g. "fa1234_product.png"
		const clean = normalizedPath.replace(/^\//, "");
		if (clean.includes("/")) {
			normalizedPath = `/api/storage/${clean}`;
		} else if (/\.(?:png|jpe?g|webp|gif|svg)$/i.test(clean)) {
			normalizedPath = `/api/storage/images/${clean}`;
		} else {
			normalizedPath = `/api/storage/${clean}`;
		}
	}

	const fullUrl = `${backendBase}${normalizedPath}`;
	return encodeURI(decodeURI(fullUrl));
}

export function isValidImageUrl(src?: string | null): boolean {
	if (!src) return false;
	const clean = src.trim().toLowerCase();
	if (
		!clean ||
		clean === "image_url" ||
		clean === "url" ||
		clean === "null" ||
		clean === "none" ||
		clean === "#" ||
		/new_image|placeholder|dummy|undefined|test_image|url_gambar|gambar_terlampir|url_/i.test(clean) ||
		clean.endsWith("/image_url") ||
		clean.endsWith("/url")
	) {
		return false;
	}
	return true;
}

export function parseBulletLines(text: string): KeyValueItem[] {
	const items: KeyValueItem[] = [];
	const lines = text.split("\n");
	for (const line of lines) {
		const match = line.match(/^[ \t]*[-*]\s*\*\*([^*]+)\*\*\s*[:–-]\s*(.+)$/);
		if (match) {
			const key = match[1].trim();
			const value = match[2].trim();
			if (
				value &&
				value.toLowerCase() !== "none" &&
				value.toLowerCase() !== "n/a" &&
				value.toLowerCase() !== "null"
			) {
				items.push({ key, value });
			}
		}
	}
	return items;
}

export function extractNodeText(node: React.ReactNode): string {
	if (!node) return "";
	if (typeof node === "string" || typeof node === "number") {
		return String(node);
	}
	if (Array.isArray(node)) {
		return node.map(extractNodeText).join(" ");
	}
	if (
		React.isValidElement(node) &&
		node.props &&
		(node.props as { children?: React.ReactNode }).children
	) {
		return extractNodeText((node.props as { children?: React.ReactNode }).children);
	}
	return "";
}

export function cleanMessageTurn(
	rawContent: string,
	currentAttachmentName?: string,
	currentAttachmentNames?: string[],
) {
	let content = rawContent || "";
	let attachmentName = currentAttachmentName;
	const names = currentAttachmentNames ? [...currentAttachmentNames] : [];

	// 1. Pattern: [SUPPLEMENTARY ATTACHED FILE CONTENT: 'filename'] ... [END OF ATTACHED FILE CONTENT]
	const suppMatch = content.match(
		/\[SUPPLEMENTARY ATTACHED FILE CONTENT:\s*['"]?([^'"\n]+)['"]?\]([\s\S]*?)\[END OF ATTACHED FILE CONTENT\]/i,
	);
	if (suppMatch) {
		const extractedName = suppMatch[1].trim();
		if (!attachmentName) attachmentName = extractedName;
		if (!names.includes(extractedName)) names.push(extractedName);
		content = content.replace(suppMatch[0], "").trim();
	}

	// 2. Pattern: --- NEWLY ATTACHED SUPPLEMENTARY FILE: 'filename' --- ... --- END OF ATTACHED FILE CONTENT ---
	const newlyMatch = content.match(
		/---\s*NEWLY ATTACHED SUPPLEMENTARY FILE:\s*['"]?([^'"\n]+)['"]?\s*---([\s\S]*?)---\s*END OF ATTACHED FILE CONTENT\s*---/i,
	);
	if (newlyMatch) {
		const extractedName = newlyMatch[1].trim();
		if (!attachmentName) attachmentName = extractedName;
		if (!names.includes(extractedName)) names.push(extractedName);
		content = content.replace(newlyMatch[0], "").trim();
	}

	return {
		content: content.trim(),
		attachmentName: attachmentName || undefined,
		attachmentNames: names.length > 0 ? names : attachmentName ? [attachmentName] : undefined,
	};
}

export function stripInternalMetadata(text?: string | null): string {
	if (!text) return "";
	let cleaned = text;

	// Strip supplementary attached file content blocks
	cleaned = cleaned.replace(
		/\[SUPPLEMENTARY ATTACHED FILE CONTENT:\s*['"]?[^'"\n]+['"]?\][\s\S]*?\[END OF ATTACHED FILE CONTENT\]/gi,
		"",
	);
	cleaned = cleaned.replace(
		/---\s*NEWLY ATTACHED SUPPLEMENTARY FILE:\s*['"]?[^'"\n]+['"]?\s*---[\s\S]*?---\s*END OF ATTACHED FILE CONTENT\s*---/gi,
		"",
	);
	cleaned = cleaned.replace(
		/\[(?:ATTACHED MEDIA ASSET URLS|ATTACHED IMAGE AVAILABLE|INSTRUCTION FOR IMAGE REPLACEMENT)[\s\S]*?\]/gi,
		"",
	);

	// Strip raw attached media asset headers e.g. ### Asset Media dari File Terlampir:
	cleaned = cleaned.replace(
		/(?:###?|\*\*)\s*(?:Asset Media dari File Terlampir|Asset Media|Media Assets|File Terlampir)[^\n]*[\s\S]*?(?=\n#{1,3}\s+|\n\*\*[^*]+\*\*|$)/gi,
		"",
	);

	// Normalize broken newline between ![alt] and (url) e.g. ![alt]\n(url) -> ![alt](url)
	cleaned = cleaned.replace(/!\[([^\]]*)\]\s*\n+\s*\(([^)]+)\)/g, "![$1]($2)");

	// Normalize unencoded spaces in markdown image links ![alt](url) -> ![alt](encodedUrl)
	cleaned = cleaned.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, rawUrl) => {
		const trimmedUrl = rawUrl.trim();
		if (trimmedUrl.includes(" ")) {
			const encoded = trimmedUrl.replace(/ /g, "%20");
			return `![${alt}](${encoded})`;
		}
		return match;
	});

	// Normalize unicode bullet symbols (•, ●, ◦) to standard markdown list syntax
	cleaned = cleaned.replace(/^[ \t]*[•●◦][ \t]*/gm, "- ");

	return cleaned.trim();
}

export function cleanDeletedItemFromMarkdown(text?: string | null, targetItem?: string | null): string {
	if (!text) return "";
	if (!targetItem || targetItem.trim().length < 2) return text;

	const target = targetItem.trim();
	const targets = target.includes(",") ? target.split(",").map((s) => s.trim()).filter(Boolean) : [target];

	let res = text;
	for (const t of targets) {
		if (t.length < 2) continue;
		const escaped = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

		// 1. Match optional preceding image tag + heading and section body
		const secRegex = new RegExp(
			`(?:^|\\n)(?:[ \\t]*!\\[[^\\]]*\\]\\([^\\)]*\\)[ \\t]*\\n\\s*)?(#{1,4}\\s*[^\\n]*${escaped}[^\\n]*\\n(?:(?!^#{1,4}\\s)[^\\n]*\\n?)*)`,
			"gim",
		);
		res = res.replace(secRegex, "\n");

		// 2. Match standalone image tag matching target
		const imgRegex = new RegExp(`(?:^|\\n)[ \\t]*!\\[[^\\]]*${escaped}[^\\]]*\\]\\([^\\)]*\\)[ \\t]*(?=\\n|$)`, "gim");
		res = res.replace(imgRegex, "");

		// 3. Match bullet point item and its nested indented lines
		const bulletRegex = new RegExp(`(?:^|\\n)[ \\t]*[\\*\\-\\+]\\s*(?:\\*\\*)?[^\\n]*${escaped}[^\\n]*(?:\\n[ \\t]{2,}[^\\n]*)*`, "gim");
		res = res.replace(bulletRegex, "");

		// 4. Match table row containing target
		const tableRegex = new RegExp(`(?:^|\\n)\\|[^\\n]*${escaped}[^\\n]*\\|?[ \\t]*(?=\\n|$)`, "gim");
		res = res.replace(tableRegex, "");

		// 5. Standalone line containing target
		const lineRegex = new RegExp(`^[^\\n]*${escaped}[^\\n]*$\\n?`, "gim");
		res = res.replace(lineRegex, "");
	}

	return res.replace(/\n{3,}/g, "\n\n").trim();
}
