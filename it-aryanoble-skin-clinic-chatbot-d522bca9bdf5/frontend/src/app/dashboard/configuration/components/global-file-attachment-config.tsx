"use client";

import { Switch } from "@/components/ui/switch";
import * as React from "react";
import { toast } from "sonner";
import { useConfigs, useUpdateConfig } from "../hooks/use-config";
import { RiLoader4Line } from "@remixicon/react";

export function GlobalFileAttachmentConfig() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();

	// Find config, default to "false" if not found
	const fileAttachmentConfig = configs?.find((c) => c.key === "AI_PROMPT_FILE_ATTACHMENTS")?.value || "false";
	const isChecked = fileAttachmentConfig === "true";

	const [isUpdating, setIsUpdating] = React.useState(false);
	const [localChecked, setLocalChecked] = React.useState(false);

	React.useEffect(() => {
		if (configs) {
			setTimeout(() => {
				setLocalChecked(isChecked);
			}, 0);
		}
	}, [configs, isChecked]);

	const handleToggle = (checked: boolean) => {
		setLocalChecked(checked);
		setIsUpdating(true);
		
		updateConfig.mutate(
			{ key: "AI_PROMPT_FILE_ATTACHMENTS", data: { value: checked.toString() } },
			{
				onSuccess: () => {
					setIsUpdating(false);
					toast.success("AI Prompt File Attachments setting updated successfully!");
				},
				onError: () => {
					// Revert on error
					setLocalChecked(!checked);
					setIsUpdating(false);
				}
			}
		);
	};

	if (isLoading) {
		return <div className="p-4 text-center text-sm text-gray-500">Loading configuration...</div>;
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
							checked={localChecked}
							onCheckedChange={handleToggle}
							disabled={updateConfig.isPending || isUpdating}
						/>
						<span className="text-sm text-black-400">
							{localChecked ? "Don't allow file attachment" : "Allow file attachment"}
						</span>
					</div>
				</div>
			</div>
		</div>
	);
}
