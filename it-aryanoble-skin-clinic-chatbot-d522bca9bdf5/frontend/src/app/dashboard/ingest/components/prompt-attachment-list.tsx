import { PromptAttachmentItem } from "./prompt-attachment-item";

interface PromptAttachmentListProps {
	files: File[];
	isLoading?: boolean;
	uploadProgress?: number;
	onRemoveFile: (index: number) => void;
}

export function PromptAttachmentList({
	files,
	isLoading,
	uploadProgress,
	onRemoveFile,
}: PromptAttachmentListProps) {
	if (files.length === 0) return null;

	return (
		<div className="flex gap-2 mb-2.5 overflow-x-auto pb-1.5 custom-scrollbar">
			{files.map((file, idx) => (
				<PromptAttachmentItem
					key={idx}
					file={file}
					isLoading={isLoading}
					uploadProgress={uploadProgress}
					onRemove={() => onRemoveFile(idx)}
				/>
			))}
		</div>
	);
}
