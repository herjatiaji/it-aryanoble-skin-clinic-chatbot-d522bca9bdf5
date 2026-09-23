import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useConfigs, useUpdateConfig } from "./use-config";

export function useFileAttachmentState() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();

	// Find config, default to "false" if not found
	const fileAttachmentConfig =
		configs?.find((c) => c.key === "AI_PROMPT_FILE_ATTACHMENTS")?.value || "false";
	const isChecked = fileAttachmentConfig === "true";

	const [isUpdating, setIsUpdating] = useState(false);
	const [localChecked, setLocalChecked] = useState(false);
	const [confirmModalOpen, setConfirmModalOpen] = useState(false);
	const [pendingChecked, setPendingChecked] = useState<boolean | null>(null);

	useEffect(() => {
		if (configs) {
			const timer = setTimeout(() => {
				setLocalChecked(isChecked);
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [configs, isChecked]);

	const handleInitiateToggle = (checked: boolean) => {
		setPendingChecked(checked);
		setConfirmModalOpen(true);
	};

	const handleConfirmToggle = () => {
		if (pendingChecked === null) return;
		const targetVal = pendingChecked;
		setIsUpdating(true);
		setLocalChecked(targetVal);

		updateConfig.mutate(
			{ key: "AI_PROMPT_FILE_ATTACHMENTS", data: { value: targetVal.toString() } },
			{
				onSuccess: () => {
					setIsUpdating(false);
					setPendingChecked(null);
					toast.success("AI Prompt File Attachments setting updated successfully!");
				},
				onError: () => {
					// Revert on error
					setLocalChecked(!targetVal);
					setPendingChecked(null);
					setIsUpdating(false);
				},
			},
		);
	};

	const handleOpenChange = (open: boolean) => {
		setConfirmModalOpen(open);
		if (!open) setPendingChecked(null);
	};

	return {
		isLoading,
		isUpdating: isUpdating || updateConfig.isPending,
		localChecked,
		confirmModalOpen,
		handleOpenChange,
		pendingChecked,
		handleInitiateToggle,
		handleConfirmToggle,
	};
}
