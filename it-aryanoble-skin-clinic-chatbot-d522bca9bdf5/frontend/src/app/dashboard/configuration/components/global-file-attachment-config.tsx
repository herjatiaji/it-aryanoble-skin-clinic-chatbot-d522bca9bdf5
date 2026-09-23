"use client";

import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { Switch } from "@/components/ui/switch";
import { RiLoader4Line } from "@remixicon/react";
import { useFileAttachmentState } from "../hooks/use-file-attachment-state";
import { ConfigCardSkeleton } from "./skeletons/config-card-skeleton";

export function GlobalFileAttachmentConfig() {
	const {
		isLoading,
		isUpdating,
		localChecked,
		confirmModalOpen,
		handleOpenChange,
		pendingChecked,
		handleInitiateToggle,
		handleConfirmToggle,
	} = useFileAttachmentState();

	if (isLoading) {
		return <ConfigCardSkeleton lines={1} />;
	}

	return (
		<div className="flex flex-col w-full">
			<div className="flex flex-col gap-6 border border-black-50 rounded-lg p-4 bg-white">
				<div className="flex flex-col gap-6.5">
					<div className="flex flex-col gap-1.5">
						<h4 className="text-base font-medium text-black-500 flex items-center gap-2">
							AI Prompt File Attachments
							{isUpdating && <RiLoader4Line className="size-4 animate-spin text-black-400" />}
						</h4>
						<p className="text-sm text-black-300">
							Allow doctors to attach files when asking the AI a question.
						</p>
					</div>

					<div className="flex items-center gap-3">
						<Switch
							id="global-file-attachment-switch"
							checked={localChecked}
							onCheckedChange={handleInitiateToggle}
							disabled={isUpdating}
							className="cursor-pointer"
						/>
						<label
							htmlFor="global-file-attachment-switch"
							className="text-sm text-black-400 cursor-pointer select-none"
						>
							{localChecked ? "Allow file attachment" : "Don't allow file attachment"}
						</label>
					</div>
				</div>
			</div>

			<ConfirmationModal
				isOpen={confirmModalOpen}
				onOpenChange={handleOpenChange}
				title={pendingChecked ? "Allow File Attachments" : "Disallow File Attachments"}
				description={
					pendingChecked
						? "Are you sure you want to allow doctors to attach files when asking questions to the AI assistant?"
						: "Are you sure you want to disallow doctors from attaching files when asking questions to the AI assistant?"
				}
				confirmText={pendingChecked ? "Allow" : "Disallow"}
				variant={pendingChecked ? "primary" : "destructive"}
				isLoading={isUpdating}
				onConfirm={handleConfirmToggle}
			/>
		</div>
	);
}
