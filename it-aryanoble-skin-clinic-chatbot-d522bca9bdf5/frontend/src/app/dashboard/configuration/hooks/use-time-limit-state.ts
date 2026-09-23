import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useConfigs, useUpdateConfig } from "./use-config";

export function useTimeLimitState() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();

	const timeLimit = configs?.find((c) => c.key === "TIME_LIMIT_PER_SESSION")?.value || "5";

	const [isEditing, setIsEditing] = useState(false);
	const [timeAmount, setTimeAmount] = useState("5");
	const [isConfirmOpen, setIsConfirmOpen] = useState(false);

	useEffect(() => {
		if (configs) {
			const timer = setTimeout(() => {
				setTimeAmount(timeLimit);
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [configs, timeLimit]);

	const handleCancel = () => {
		setIsEditing(false);
		setTimeAmount(timeLimit);
	};

	const handleConfirmSave = () => {
		updateConfig.mutate(
			{ key: "TIME_LIMIT_PER_SESSION", data: { value: timeAmount } },
			{
				onSuccess: () => {
					setIsEditing(false);
					setIsConfirmOpen(false);
					toast.success("Time limit per session updated successfully!");
				},
			},
		);
	};

	return {
		isLoading,
		isPending: updateConfig.isPending,
		isEditing,
		setIsEditing,
		timeAmount,
		setTimeAmount,
		isConfirmOpen,
		setIsConfirmOpen,
		handleCancel,
		handleConfirmSave,
	};
}
