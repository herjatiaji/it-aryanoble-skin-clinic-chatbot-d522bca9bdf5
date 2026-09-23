import { getErrorMessage } from "@/lib/utils";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useConfigs, useFetchModels, useUpdateConfig } from "./use-config";

export function useModelConfigState() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();
	const fetchModels = useFetchModels();

	const [isEditing, setIsEditing] = useState(false);
	const [showKeys, setShowKeys] = useState(false);
	const [isConfirmOpen, setIsConfirmOpen] = useState(false);

	// Form state
	const [activeProvider, setActiveProvider] = useState("openai");
	const [modelName, setModelName] = useState("");
	const [apiKey, setApiKey] = useState("");
	const [availableModels, setAvailableModels] = useState<
		{ id: string; input_limit?: number; output_limit?: number }[]
	>([]);

	const syncFromConfigs = useCallback(() => {
		if (configs) {
			setActiveProvider(
				(configs.find((c) => c.key === "LLM_ACTIVE_PROVIDER")?.value as string) || "openai",
			);
			setModelName((configs.find((c) => c.key === "LLM_ACTIVE_MODEL_NAME")?.value as string) || "");
			setApiKey((configs.find((c) => c.key === "LLM_API_KEY")?.value as string) || "");
		}
	}, [configs]);

	useEffect(() => {
		if (configs && !isEditing) {
			const timer = setTimeout(() => {
				syncFromConfigs();
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [configs, isEditing, syncFromConfigs]);

	const handleFetchModels = async () => {
		if (!apiKey) return;
		try {
			const models = await fetchModels.mutateAsync({
				provider: activeProvider,
				api_key: apiKey,
			});
			setAvailableModels(models);
			toast.success("Models fetched successfully!");
		} catch (error) {
			setAvailableModels([]);
			toast.error(getErrorMessage(error, "Failed to fetch models."));
		}
	};

	const handleCancel = () => {
		setIsEditing(false);
		setAvailableModels([]);
		syncFromConfigs();
	};

	const handleInitiateSave = () => {
		if (!modelName) {
			toast.error("Please select a model.");
			return;
		}
		if (!apiKey) {
			toast.error("Please enter an API key.");
			return;
		}
		setIsConfirmOpen(true);
	};

	const handleSave = async () => {
		if (!modelName) {
			toast.error("Please select a model.");
			return;
		}

		try {
			await updateConfig.mutateAsync({
				key: "LLM_ACTIVE_PROVIDER",
				data: { value: activeProvider },
			});
			await updateConfig.mutateAsync({
				key: "LLM_ACTIVE_MODEL_NAME",
				data: { value: modelName },
			});
			await updateConfig.mutateAsync({
				key: "LLM_API_KEY",
				data: { value: apiKey },
			});

			setIsEditing(false);
			toast.success("AI Model Configuration saved successfully!");
		} catch (error) {
			toast.error(getErrorMessage(error, "Failed to save AI configuration."));
		}
	};

	return {
		isLoading,
		isUpdating: updateConfig.isPending,
		isFetchingModels: fetchModels.isPending,
		isEditing,
		setIsEditing,
		showKeys,
		setShowKeys,
		isConfirmOpen,
		setIsConfirmOpen,
		activeProvider,
		setActiveProvider,
		modelName,
		setModelName,
		apiKey,
		setApiKey,
		availableModels,
		setAvailableModels,
		handleFetchModels,
		handleCancel,
		handleInitiateSave,
		handleSave,
	};
}
