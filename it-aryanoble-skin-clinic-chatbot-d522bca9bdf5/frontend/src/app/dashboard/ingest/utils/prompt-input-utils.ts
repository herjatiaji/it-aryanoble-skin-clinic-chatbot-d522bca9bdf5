import {
	RiFileExcel2Line,
	RiFilePdf2Line,
	RiFilePpt2Line,
	RiFileTextLine,
	RiFileWord2Line,
	RiImage2Line,
} from "@remixicon/react";
import { toast } from "sonner";

export const ACCEPTED_FILE_EXTENSIONS = [
	".docx",
	".pptx",
	".xlsx",
	".pdf",
	".txt",
	".csv",
	".png",
	".jpg",
	".jpeg",
	".webp",
];

export const ACCEPT_STRING = ACCEPTED_FILE_EXTENSIONS.join(",");

export function validateAndFilterFiles(files: File[]): File[] {
	const validFiles: File[] = [];
	for (const file of files) {
		const lowerName = file.name.toLowerCase();
		if (lowerName.endsWith(".doc") || lowerName.endsWith(".ppt") || lowerName.endsWith(".xls")) {
			toast.error(
				`Legacy format detected in "${file.name}". Please save as .docx, .pptx, or .xlsx before uploading.`,
			);
			continue;
		}
		const isSupportedExt = ACCEPTED_FILE_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
		const isImageMime = file.type.startsWith("image/");
		const isDocMime =
			file.type === "application/pdf" ||
			file.type === "text/plain" ||
			file.type === "text/csv" ||
			file.type.includes("openxmlformats");

		if (!isSupportedExt && !isImageMime && !isDocMime) {
			toast.error(
				`Unsupported file format: "${file.name}". Supported formats: .docx, .pptx, .xlsx, .pdf, .txt, .csv, and images.`,
			);
			continue;
		}

		const MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024; // 500 MB
		if (file.size > MAX_FILE_SIZE_BYTES) {
			const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
			toast.error(`File "${file.name}" (${sizeMb} MB) melebihi batas maksimal upload 500 MB.`);
			continue;
		}

		// If pasted from clipboard without proper extension, normalize filename
		if (isImageMime && !isSupportedExt) {
			const ext = file.type.split("/")[1] || "png";
			const normalizedFile = new File([file], `pasted_image_${Date.now()}.${ext}`, {
				type: file.type,
			});
			validFiles.push(normalizedFile);
		} else {
			validFiles.push(file);
		}
	}
	return validFiles;
}

export function getFileIconAndColor(filename?: string | null) {
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
		case "png":
		case "jpg":
		case "jpeg":
		case "gif":
		case "webp":
			return { Icon: RiImage2Line, bgColor: "bg-purple-50", textColor: "text-purple-600" };
		case "txt":
		default:
			return { Icon: RiFileTextLine, bgColor: "bg-blue-50", textColor: "text-blue-600" };
	}
}

export function formatFileSize(bytes?: number | null): string {
	if (!bytes || bytes <= 0) return "0 B";
	if (bytes >= 1024 * 1024 * 1024) {
		return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB";
	}
	if (bytes >= 1024 * 1024) {
		return (bytes / (1024 * 1024)).toFixed(1) + " MB";
	}
	if (bytes >= 1024) {
		return (bytes / 1024).toFixed(1) + " KB";
	}
	return bytes + " B";
}
