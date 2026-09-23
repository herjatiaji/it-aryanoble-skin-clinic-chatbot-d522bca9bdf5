/**
 * Formats a raw number or numeric string with thousand commas (e.g. 3000000 -> "3,000,000").
 */
export function formatNumberWithCommas(value: number | string | null | undefined): string {
	if (value === null || value === undefined || value === "") return "";
	const numStr = String(value).replace(/[^0-9]/g, "");
	if (!numStr) return "";
	const num = parseInt(numStr, 10);
	if (isNaN(num)) return "";
	return num.toLocaleString("en-US");
}

/**
 * Parses a comma-separated or raw string into an integer number (e.g. "3,000,000" -> 3000000).
 */
export function parseRawNumber(formattedValue: string | number | null | undefined): number {
	if (formattedValue === null || formattedValue === undefined || formattedValue === "") return 0;
	if (typeof formattedValue === "number")
		return isNaN(formattedValue) ? 0 : Math.max(0, formattedValue);
	const cleanStr = formattedValue.replace(/[^0-9]/g, "");
	if (!cleanStr) return 0;
	const parsed = parseInt(cleanStr, 10);
	return isNaN(parsed) ? 0 : parsed;
}

/**
 * Returns a human-friendly compact representation of a token count (e.g. 3000000 -> "3M", 500000 -> "500K", 1500000 -> "1.5M").
 */
export function formatCompactTokens(value: number | string | null | undefined): string {
	const num = typeof value === "number" ? value : parseRawNumber(value);
	if (!num || num === 0) return "0";

	if (num >= 1_000_000_000) {
		const val = num / 1_000_000_000;
		return `${Number(val.toFixed(2))}B`;
	}
	if (num >= 1_000_000) {
		const val = num / 1_000_000;
		return `${Number(val.toFixed(2))}M`;
	}
	if (num >= 1_000) {
		const val = num / 1_000;
		return `${Number(val.toFixed(2))}K`;
	}
	return num.toLocaleString("en-US");
}

/**
 * Returns a full descriptive phrase for tokens (e.g. 3000000 -> "3 Million tokens").
 */
export function formatTokenHumanDescription(value: number | string | null | undefined): string {
	const num = typeof value === "number" ? value : parseRawNumber(value);
	if (!num || num === 0) return "0 tokens";

	if (num >= 1_000_000_000) {
		const val = num / 1_000_000_000;
		return `${Number(val.toFixed(2))} Billion tokens`;
	}
	if (num >= 1_000_000) {
		const val = num / 1_000_000;
		return `${Number(val.toFixed(2))} Million tokens`;
	}
	if (num >= 1_000) {
		const val = num / 1_000;
		return `${Number(val.toFixed(2))} Thousand tokens`;
	}
	return `${num.toLocaleString("en-US")} tokens`;
}
