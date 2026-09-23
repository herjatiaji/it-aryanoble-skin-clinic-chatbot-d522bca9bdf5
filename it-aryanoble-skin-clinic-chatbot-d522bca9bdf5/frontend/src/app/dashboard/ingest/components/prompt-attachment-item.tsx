import {
	Attachment,
	AttachmentAction,
	AttachmentActions,
	AttachmentContent,
	AttachmentMedia,
	AttachmentTitle,
} from "@/components/ui/attachment";
import { cn } from "@/lib/utils";
import { RiCloseLine, RiLoader4Line } from "@remixicon/react";
import { formatFileSize, getFileIconAndColor } from "../utils/prompt-input-utils";

interface PromptAttachmentItemProps {
	file: File;
	isLoading?: boolean;
	uploadProgress?: number;
	onRemove: () => void;
}

export function PromptAttachmentItem({
	file,
	isLoading,
	uploadProgress,
	onRemove,
}: PromptAttachmentItemProps) {
	const { Icon, bgColor, textColor } = getFileIconAndColor(file.name);

	return (
		<Attachment
			className={cn(
				"bg-white border border-zinc-200 shadow-none p-2 min-w-44 max-w-64 shrink-0 rounded-lg transition-all",
				isLoading && "border-blue-300 bg-blue-50/20",
			)}
		>
			<AttachmentMedia className={cn(bgColor, textColor, "rounded-lg p-2 shrink-0")}>
				{isLoading ? (
					<RiLoader4Line className="w-5 h-5 animate-spin text-blue-600" />
				) : (
					<Icon className="w-5 h-5" />
				)}
			</AttachmentMedia>
			<AttachmentContent className="overflow-hidden min-w-0 pr-1 flex-1">
				<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate block">
					{file.name}
				</AttachmentTitle>
				<div className="flex items-center justify-between gap-1 text-[11px] text-zinc-500 mt-0.5">
					<span>{formatFileSize(file.size)}</span>
					{isLoading && uploadProgress !== undefined && (
						<span className="font-semibold text-blue-600">
							{uploadProgress >= 100
								? "Processing..."
								: uploadProgress > 0
									? `${uploadProgress}%`
									: "Uploading..."}
						</span>
					)}
				</div>
				{isLoading && uploadProgress !== undefined && (
					<div className="w-full h-1 bg-blue-100 rounded-full overflow-hidden mt-1.5">
						<div
							className="h-full bg-blue-600 transition-all duration-200 rounded-full"
							style={{ width: `${Math.max(8, uploadProgress)}%` }}
						/>
					</div>
				)}
			</AttachmentContent>
			{!isLoading && (
				<AttachmentActions>
					<AttachmentAction
						variant="ghost"
						className="hover:bg-zinc-100 text-zinc-500 hover:text-zinc-950 ml-1 rounded-md"
						onClick={onRemove}
					>
						<RiCloseLine className="w-4 h-4" />
					</AttachmentAction>
				</AttachmentActions>
			)}
		</Attachment>
	);
}
