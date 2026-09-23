export function formatItemName(name: string, count: number): string {
	if (count === 1) {
		const lower = name.toLowerCase();
		if (lower === "categories") return "category";
		if (lower === "queries") return "query";
		if (lower === "histories") return "history";
		if (lower.endsWith("ies")) return name.slice(0, -3) + "y";
		if (
			lower.endsWith("ses") ||
			lower.endsWith("shes") ||
			lower.endsWith("ches") ||
			lower.endsWith("xes")
		) {
			return name.slice(0, -2);
		}
		if (lower.endsWith("s") && !lower.endsWith("ss")) return name.slice(0, -1);
		return name;
	}
	return name;
}

export function calculatePaginationRange(
	page: number,
	totalPages: number,
	delta = 1,
): (number | string)[] {
	const range: (number | string)[] = [];

	if (totalPages <= 7) {
		for (let i = 1; i <= totalPages; i++) {
			range.push(i);
		}
		return range;
	}

	const left = Math.max(2, page - delta);
	const right = Math.min(totalPages - 1, page + delta);

	range.push(1);

	if (left > 2) {
		range.push("ellipsis-left");
	}

	for (let i = left; i <= right; i++) {
		range.push(i);
	}

	if (right < totalPages - 1) {
		range.push("ellipsis-right");
	}

	range.push(totalPages);

	return range;
}
