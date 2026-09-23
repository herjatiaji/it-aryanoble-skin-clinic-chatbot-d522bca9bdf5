import {
	RiFileExcel2Line,
	RiFilePdf2Line,
	RiFilePpt2Line,
	RiFileTextLine,
	RiFileWord2Line,
	RiImage2Line,
} from "@remixicon/react";

export const getFileIconAndColor = (filename?: string | null) => {
	if (!filename) return { Icon: RiFileTextLine, bgColor: "bg-blue-50", textColor: "text-blue-600" };
	const ext = filename.split(".").pop()?.toLowerCase() || "";
	switch (ext) {
		case "pdf":
			return { Icon: RiFilePdf2Line, bgColor: "bg-red-50", textColor: "text-red-600" };
		case "doc":
		case "docx":
			return { Icon: RiFileWord2Line, bgColor: "bg-blue-50", textColor: "text-blue-600" };
		case "xls":
		case "xlsx":
		case "csv":
			return { Icon: RiFileExcel2Line, bgColor: "bg-emerald-50", textColor: "text-emerald-600" };
		case "ppt":
		case "pptx":
		case "pps":
		case "ppsx":
		case "pot":
		case "potx":
		case "odp":
			return { Icon: RiFilePpt2Line, bgColor: "bg-orange-50", textColor: "text-orange-600" };
		case "jpg":
		case "jpeg":
		case "png":
		case "webp":
			return { Icon: RiImage2Line, bgColor: "bg-purple-50", textColor: "text-purple-600" };
		default:
			return { Icon: RiFileTextLine, bgColor: "bg-blue-50", textColor: "text-blue-600" };
	}
};

export const IGNORED_METADATA_KEYS = new Set([
	"page",
	"score",
	"relevance",
	"similarity",
	"distance",
	"rank",
	"type",
	"source",
	"category",
	"doc_id",
	"knowledge_id",
	"id",
	"status",
	"timestamp",
	"created_at",
	"updated_at",
]);

export const getAttachmentNames = (
	attachments?: Record<string, unknown> | null,
	role?: string,
): string[] => {
	if (role?.toUpperCase() === "ASSISTANT") {
		return [];
	}
	if (!attachments) return [];
	if (Array.isArray(attachments)) {
		return attachments
			.map((item) => (typeof item === "string" ? item : String(item?.name || item?.filename || "")))
			.filter((name) => Boolean(name) && !IGNORED_METADATA_KEYS.has(name.toLowerCase()));
	}
	if (typeof attachments === "object") {
		if (Array.isArray(attachments.names)) {
			return (attachments.names as string[]).filter(
				(name) => Boolean(name) && !IGNORED_METADATA_KEYS.has(name.toLowerCase()),
			);
		}
		return Object.keys(attachments).filter(
			(key) => Boolean(key) && !IGNORED_METADATA_KEYS.has(key.toLowerCase()),
		);
	}
	return [];
};
