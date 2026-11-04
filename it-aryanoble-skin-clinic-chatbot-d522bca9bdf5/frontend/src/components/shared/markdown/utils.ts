import React from "react";
import type { KeyValueItem } from "./types";

export function resolveImageUrl(src?: string | null): string {
	if (!src) return "";
	let trimmed = src.trim();

	// Normalize hallucinated `https://api.storage/`, `https://api/`, or `/api/storage/` prefixes
	trimmed = trimmed.replace(/^https?:\/\/api(?:\.storage)?(?:\/storage)?\//i, "/api/storage/");
	trimmed = trimmed.replace(/^\/api\/api\/storage\//i, "/api/storage/");

	if (trimmed.startsWith("/storage/")) {
		trimmed = `/api${trimmed}`;
	}

	const backendBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(
		/\/api\/?$/,
		"",
	);

	// If URL contains an internal backend host (localhost, 127.0.0.1, minio, backend, api.storage, api) or storage path, normalize to relative path first
	const isInternalHost = /^(?:https?:\/\/)?(?:localhost|127\.0\.0\.1|minio|backend|api\.storage|api)(?::\d+)?/i.test(trimmed);
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

	// Normalize Private Use Area (PUA) bullet glyphs and broken font boxes (U+F0B7, U+FFFD, etc.)
	cleaned = cleaned.replace(/[\uF0B7\uF0A7\uF06C\uF0A8\uF0D8\uF076]/g, "•");
	cleaned = cleaned.replace(/\uF0FC/g, "✓");
	cleaned = cleaned.replace(/\uF0E0/g, "→");
	// Replace any remaining PUA or box glyphs at boundaries with bullet, else strip
	cleaned = cleaned.replace(/(?:^|[ \t|*#-])[\uE000-\uF8FF\uFFFD\u25AF\u25A1]+/gm, (match) => {
		const prefix = match.slice(0, -match.trimStart().length);
		return `${prefix}• `;
	});
	cleaned = cleaned.replace(/[\uE000-\uF8FF\uFFFD\u25AF\u25A1]/g, "");

	// Convert literal HTML linebreaks (<br>, <br/>) to safe sentinel (\u241E) for JSX rendering
	cleaned = cleaned.replace(/<br\s*\/?>/gi, "\u241E");
	// Strip raw sub / sup / small tags that ReactMarkdown cannot parse without rehype-raw
	cleaned = cleaned.replace(/<\/?(?:sub|sup|small)>/gi, "");

	// Normalize discontinue phrase if dash was used (e.g. 'Per 12 Juni-stok klinik habis')
	// (Answer-side status wording is grounded against evidence in the backend: ground_status_claims)
	cleaned = cleaned.replace(
		/\b((?:per|sejak|mulai)\s+\d{1,2}\s+[A-Za-z]{3,}(?:\s+\d{4})?)\s*[-–—]\s*(stok\s+(?:klinik\s+)?habis)/gi,
		"$1 sampai dengan $2"
	);

	// Auto-heal GFM markdown tables
	cleaned = repairMarkdownTables(cleaned);

	// Normalize ordered list numbering across images and visual breaks
	cleaned = normalizeOrderedListNumbering(cleaned);

	return cleaned.trim();
}

const TABLE_REPAIR_CACHE = new Map<string, string>();
const MAX_TABLE_CACHE_SIZE = 40;

function computeTableCacheKey(text: string): string {
	const len = text.length;
	if (len < 5000) return text;
	const head = text.slice(0, 120);
	const mid = text.slice(Math.floor(len / 2) - 60, Math.floor(len / 2) + 60);
	const tail = text.slice(-120);
	return `${len}__${head}__${mid}__${tail}`;
}

/**
 * Universal auto-healer for GitHub Flavored Markdown (GFM) tables in the frontend.
 */
export function repairMarkdownTables(text?: string | null): string {
	if (!text || !text.includes("|")) return text || "";

	const cacheKey = computeTableCacheKey(text);
	const cached = TABLE_REPAIR_CACHE.get(cacheKey);
	if (cached !== undefined) {
		return cached;
	}

	// Normalize raw <br> tags and escaped &lt;br&gt; to \u241E sentinel so JSX renderers resolve them as <br />
	let s = text.replace(/<br\s*\/?>/gi, "\u241E").replace(/&lt;br\s*\/?&gt;/gi, "\u241E");

	// 0. Separate lines with prefixes (bullets/text) before table rows
	// e.g. `- New Services | No. | Nama Tindakan | Nama Alat | | ---` -> `- New Services\n\n| No. | ...`
	s = s.replace(
		/^([ \t]*(?:[-*•●◦]\s+)?[^|\n]+?)[ \t]*(\|[ \t]*[^|\n]+(?:[ \t]*\|[ \t]*[^|\n]+)+[ \t]*\|?.*)$/gm,
		(match, prefix, tablePart) => {
			const p = prefix.trim();
			const t = tablePart.trim();
			if (t.includes("---") || /\|[ \t]*\d+[ \t]*\|/.test(t) || (t.startsWith("|") && t.split("|").length >= 3)) {
				return `${p}\n\n${t}`;
			}
			return match;
		},
	);

	// 1. Separate glued delimiters and rows
	// A. Delimiter row glued to header row or another line:
	// e.g. `| Col 1 | Col 2 || ---` -> `| Col 1 | Col 2 |\n| ---`
	s = s.replace(/\|[ \t]*\|(?=[ \t]*:?-{3,})/g, "|\n|");

	// B. Data row glued after delimiter row:
	// e.g. `| --- | --- || 1 |` -> `| --- | --- |\n| 1 |`
	s = s.replace(/((?:\s*:?-{3,}:?\s*\|)+)[ \t]*\|(?=[ \t]*[^|\n])/g, "$1\n|");

	// C. Consecutive rows glued together with `| |` or `||`
	// Separate glued || between data rows (e.g. `| Shampoo | ![img] || Hair Mask | ![img] |`)
	s = s.replace(/\|{2,}(?=[ \t]*[^|\n:])/g, "|\n|");
	// First, numbered rows:
	s = s.replace(/\|[ \t]*\|(?=[ \t]*\d+[ \t]*\|)/g, "|\n|");

	const rawLines = s.split("\n");
	const processedLines: string[] = [];

	for (let i = 0; i < rawLines.length; i++) {
		let trimmed = rawLines[i].trim();

		// Check if line contains multiple glued numbered rows (e.g. `| 5 |||| 6 |||| 7 |||`)
		if (trimmed.startsWith("|") && /\|[ \t]*\d+[ \t]*\|.*\|[ \t]*\d+[ \t]*\|/.test(trimmed)) {
			const parts = trimmed.split(/(?<=\|)[ \t]*(?=\|[ \t]*\d+[ \t]*\|)/);
			for (const p of parts) {
				const pClean = p.trim();
				if (pClean) processedLines.push(pClean);
			}
			continue;
		}

		// Normalize runs of 3+ glued pipes (OCR/parser boundary artifacts like `||||||||||`) into a single pipe
		const isDelim = /^\|?(?:\s*:?-{3,}:?\s*\|?)+$/.test(trimmed);
		if (!isDelim && trimmed.startsWith("|")) {
			trimmed = trimmed.replace(/\|{3,}/g, "|");
		}

		processedLines.push(trimmed);
	}

	// 2. Merge split or partial delimiter rows (e.g. `| ---` followed by `| --- | --- |` even across blank lines)
	const mergedLines: string[] = [];
	let idx = 0;
	while (idx < processedLines.length) {
		const line = processedLines[idx].trim();
		const isDelimLine = /^\|?(?:\s*:?-{3,}:?\s*\|?)+$/.test(line);
		if (isDelimLine) {
			let j = idx + 1;
			while (j < processedLines.length && processedLines[j].trim() === "") {
				j++;
			}
			if (j < processedLines.length && /^\|?(?:\s*:?-{3,}:?\s*\|?)+$/.test(processedLines[j].trim())) {
				const cellsCurr = line.split("|").map((c) => c.trim()).filter(Boolean);
				const cellsNext = processedLines[j].trim().split("|").map((c) => c.trim()).filter(Boolean);
				const allDelim = cellsCurr.concat(cellsNext);
				mergedLines.push("| " + allDelim.join(" | ") + " |");
				idx = j + 1;
				continue;
			}
		}
		mergedLines.push(processedLines[idx]);
		idx += 1;
	}

	// 3. Block-level Table Parser & Normalizer
	const finalLines: string[] = [];
	let i = 0;
	let lastTableHeaders: string[] | null = null;

	const isRow = (lineStr: string) => {
		const l = lineStr.trim();
		return l.startsWith("|") && (l.endsWith("|") || l.includes("---"));
	};

	const extractCells = (lineStr: string) => {
		let l = lineStr.trim();
		if (!l.endsWith("|")) l = l + " |";
		while (l.includes("||")) {
			l = l.replace(/\|\|/g, "|  |");
		}
		return l.split("|").slice(1, -1).map((c) => c.trim());
	};

	const isDelimRow = (cells: string[]) => {
		return cells.length > 0 && cells.every((c) => !c || /^:?-{3,}:?$/.test(c));
	};

	while (i < mergedLines.length) {
		const origL = mergedLines[i];
		const cleanL = origL.trim();

		if (!isRow(cleanL)) {
			finalLines.push(origL);
			i++;
			continue;
		}

		// Found a table row! Collect all consecutive table rows
		const tableRawRows: string[] = [];
		while (i < mergedLines.length && isRow(mergedLines[i])) {
			tableRawRows.push(mergedLines[i].trim());
			i++;
		}

		if (tableRawRows.length === 0) continue;

		const parsedRows = tableRawRows.map(extractCells);

		let headerCells: string[] | null = null;
		let bodyRows: string[][] = [];

		if (parsedRows.length === 1) {
			const firstCells = parsedRows[0];
			if (isDelimRow(firstCells)) continue;
			const cols = Math.max(firstCells.length, 1);
			headerCells = Array.from({ length: cols }, (_, cIdx) => `Kolom ${cIdx + 1}`);
			bodyRows = [firstCells];
		} else {
			const firstRow = parsedRows[0];
			const secondRow = parsedRows[1];

			if (isDelimRow(firstRow)) {
				const cols = Math.max(firstRow.length, 1);
				headerCells = Array.from({ length: cols }, (_, cIdx) => `Kolom ${cIdx + 1}`);
				bodyRows = parsedRows.slice(1);
			} else if (isDelimRow(secondRow)) {
				headerCells = firstRow;
				bodyRows = parsedRows.slice(2);
			} else {
				const firstVal = firstRow[0] || "";
				const isNum = /^\d+$/.test(firstVal);
				if (isNum) {
					const cols = Math.max(firstRow.length, 2);
					const hdrs = ["No."];
					for (let ci = 1; ci < cols; ci++) {
						hdrs.push(ci === 1 ? "Nama Tindakan / Keterangan" : `Detail ${ci}`);
					}
					headerCells = hdrs;
					bodyRows = parsedRows;
				} else {
					headerCells = firstRow;
					bodyRows = parsedRows.slice(1);
				}
			}
		}

		// Unpack glued body rows if cell count is a multiple of header count
		const unpackedBodyRows: string[][] = [];
		for (const b of bodyRows) {
			if (!isDelimRow(b) && b.length > headerCells.length && b.length % headerCells.length === 0) {
				for (let k = 0; k < b.length; k += headerCells.length) {
					unpackedBodyRows.push(b.slice(k, k + headerCells.length));
				}
			} else {
				unpackedBodyRows.push(b);
			}
		}
		bodyRows = unpackedBodyRows;

		// Prune trailing phantom empty columns
		let maxActiveCol = headerCells.length;
		for (const r of bodyRows) {
			maxActiveCol = Math.max(maxActiveCol, r.length);
		}

		while (maxActiveCol > 1) {
			const colIdx = maxActiveCol - 1;
			const hdrEmpty = colIdx >= headerCells.length || !headerCells[colIdx];
			const allBodyEmpty = bodyRows.every((r) => colIdx >= r.length || !r[colIdx]);
			if (hdrEmpty && allBodyEmpty) {
				maxActiveCol--;
			} else {
				break;
			}
		}

		const targetCols = Math.max(maxActiveCol, 1);

		const paddedHeaders = headerCells.slice(0, targetCols);
		while (paddedHeaders.length < targetCols) {
			paddedHeaders.push(paddedHeaders.length > 1 ? `Keterangan ${paddedHeaders.length + 1}` : "Keterangan");
		}
		for (let hI = 0; hI < paddedHeaders.length; hI++) {
			if (!paddedHeaders[hI]) {
				paddedHeaders[hI] = hI === 0 ? "Parameter" : (hI === 1 ? "Keterangan" : `Kolom ${hI + 1}`);
			}
		}

		const paddedDelims = Array.from({ length: targetCols }, () => "---");

		const cleanedBody: string[][] = [];
		for (const r of bodyRows) {
			const rTrimmed = r.slice(0, targetCols);
			while (rTrimmed.length < targetCols) {
				rTrimmed.push("");
			}
			if (rTrimmed.some(Boolean)) {
				cleanedBody.push(rTrimmed);
			}
		}

		// Merge complementary sparse split rows
		const mergedBody: string[][] = [];
		for (const r of cleanedBody) {
			if (mergedBody.length > 0) {
				const prevR = mergedBody[mergedBody.length - 1];
				const overlap = prevR.some((c1, idx) => c1 && r[idx]);
				const prevHas = prevR.some(Boolean);
				const currHas = r.some(Boolean);
				if (!overlap && prevHas && currHas) {
					mergedBody[mergedBody.length - 1] = prevR.map((c1, idx) => c1 || r[idx] || "");
					continue;
				}
			}
			mergedBody.push(r);
		}

		// Merge consecutive tables with identical header
		let canMerge = false;
		if (lastTableHeaders && lastTableHeaders.length === paddedHeaders.length) {
			if (lastTableHeaders.every((h1, idx) => h1.trim().toLowerCase() === paddedHeaders[idx].trim().toLowerCase())) {
				let k = finalLines.length - 1;
				while (k >= 0 && finalLines[k].trim() === "") {
					k--;
				}
				if (k >= 0 && finalLines[k].startsWith("|")) {
					canMerge = true;
				}
			}
		}

		if (canMerge) {
			while (finalLines.length > 0 && finalLines[finalLines.length - 1].trim() === "") {
				finalLines.pop();
			}
			for (const r of mergedBody) {
				finalLines.push("| " + r.join(" | ") + " |");
			}
		} else {
			if (finalLines.length > 0 && finalLines[finalLines.length - 1].trim() !== "") {
				finalLines.push("");
			}

			finalLines.push("| " + paddedHeaders.join(" | ") + " |");
			finalLines.push("| " + paddedDelims.join(" | ") + " |");
			for (const r of mergedBody) {
				finalLines.push("| " + r.join(" | ") + " |");
			}

			lastTableHeaders = paddedHeaders;
		}

		finalLines.push("");
	}

	const result = finalLines.join("\n");
	if (TABLE_REPAIR_CACHE.size >= MAX_TABLE_CACHE_SIZE) {
		const oldestKey = TABLE_REPAIR_CACHE.keys().next().value;
		if (oldestKey) TABLE_REPAIR_CACHE.delete(oldestKey);
	}
	TABLE_REPAIR_CACHE.set(cacheKey, result);
	return result;
}

/**
 * Normalizes ordered list numbering across visual breaks (such as standalone images,
 * blank lines, or sub-bullets) so that lists maintain a continuous, monotonic numbering
 * sequence (1, 2, 3, ...) instead of resetting back to 1.
 * Also indents standalone markdown images that directly follow an ordered list item
 * so CommonMark keeps them within the parent list item (preventing AST fragmentation).
 */
export function normalizeOrderedListNumbering(markdown: string): string {
	if (!markdown) return "";

	const lines = markdown.split("\n");
	const result: string[] = [];
	let currentExpectedNumber = 0;
	let inList = false;

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i];
		const match = line.match(/^(\s{0,2})(\d+)\.\s+(.*)$/);

		if (match) {
			const indent = match[1];
			const rest = match[3];

			if (!inList) {
				inList = true;
				currentExpectedNumber = 1;
			} else {
				currentExpectedNumber++;
			}

			result.push(`${indent}${currentExpectedNumber}. ${rest}`);
			continue;
		}

		// Reset list tracking upon encountering structural section dividers or headings
		const isHeading = /^\s*#{1,6}\s+/.test(line);
		const isHorizontalRule = /^\s*(?:---|\*\*\*|___)\s*$/.test(line);
		const isTable = /^\s*\|/.test(line);

		if (isHeading || isHorizontalRule || isTable) {
			inList = false;
			currentExpectedNumber = 0;
			result.push(line);
			continue;
		}

		// If we are inside an active ordered list and encounter a standalone image:
		// Indent the image by 3 spaces so CommonMark treats it as part of the current list item
		const imageMatch = line.match(/^(\s*)!\[([^\]]*)\]\(([^)]+)\)\s*$/);
		if (inList && imageMatch && imageMatch[1].length < 3) {
			result.push(`   ${imageMatch[0].trim()}`);
			continue;
		}

		// Check if a line is a blank line, sub-bullet, or indented block (which does not break the list)
		const isBlank = line.trim() === "";
		const isBulletOrIndented = /^\s*(?:[-*•]|\s{2,})/.test(line);

		if (!isBlank && !isBulletOrIndented) {
			let hasSubsequentListItem = false;
			for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
				if (/^\s{0,2}\d+\.\s+/.test(lines[j])) {
					hasSubsequentListItem = true;
					break;
				}
				if (/^\s*#{1,6}\s+/.test(lines[j])) break;
			}

			if (!hasSubsequentListItem) {
				inList = false;
				currentExpectedNumber = 0;
			}
		}

		result.push(line);
	}

	return result.join("\n");
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
