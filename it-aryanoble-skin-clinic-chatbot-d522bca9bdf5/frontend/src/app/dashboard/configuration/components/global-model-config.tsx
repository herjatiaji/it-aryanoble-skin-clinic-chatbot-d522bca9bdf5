"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { RiCheckLine, RiEdit2Line, RiLoader4Line, RiEyeLine, RiEyeOffLine, RiInformationFill, RiRefreshLine } from "@remixicon/react";
import * as React from "react";
import { useConfigs, useUpdateConfig, useFetchModels } from "../hooks/use-config";
import { toast } from "sonner";
import { getErrorMessage } from "@/lib/utils";

export function GlobalModelConfig() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();
	const fetchModels = useFetchModels();

	const [isEditing, setIsEditing] = React.useState(false);
	const [showKeys, setShowKeys] = React.useState(false);

	// Form state
	const [activeProvider, setActiveProvider] = React.useState("openai");
	const [modelName, setModelName] = React.useState("");
	const [apiKey, setApiKey] = React.useState("");
	
	const [availableModels, setAvailableModels] = React.useState<{ id: string; input_limit?: number; output_limit?: number }[]>([]);

	React.useEffect(() => {
		if (configs) {
			setTimeout(() => {
				setActiveProvider(
					(configs.find((c) => c.key === "LLM_ACTIVE_PROVIDER")?.value as string) || "openai",
				);
				setModelName(
					(configs.find((c) => c.key === "LLM_ACTIVE_MODEL_NAME")?.value as string) || "",
				);
				setApiKey((configs.find((c) => c.key === "LLM_API_KEY")?.value as string) || "");
			}, 0);
		}
	}, [configs]);



	const inputClass = "bg-black-50 border-black-50 text-black-500";

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
			await updateConfig.mutateAsync({ key: "LLM_ACTIVE_MODEL_NAME", data: { value: modelName } });
			await updateConfig.mutateAsync({ key: "LLM_API_KEY", data: { value: apiKey } });

			setIsEditing(false);
			toast.success("AI Model Configuration saved successfully!");
		} catch (error) {
			toast.error(getErrorMessage(error, "Failed to save AI configuration."));
			console.error("Save failed", error);
		}
	};

	if (isLoading) {
		return <div className="p-4 text-center text-sm text-gray-500">Loading AI configuration...</div>;
	}


	return (
		<div className="flex flex-col w-full">
			<div className="flex flex-col gap-6 border border-black-50 rounded-lg p-4 bg-white">
				{/* Top Part: Title and Edit Button */}
				<div className="flex justify-between items-start">
					<div className="flex flex-col gap-1">
						<h3 className="text-base font-medium text-black-500">Global AI Model Configuration</h3>
						<p className="text-sm text-black-300">
							Configure the default LLM provider, active model, and API key for the chatbot.
						</p>
					</div>
					<div className="flex items-center gap-2">
						{isEditing ? (
							<>
								<Button
									variant="ghost"
									className="text-black-500 hover:text-black-600 hover:bg-zinc-100 px-5 rounded-lg font-medium"
									onClick={() => {
										setIsEditing(false);
										setAvailableModels([]);
										// Reset state
										if (configs) {
											setActiveProvider(
												(configs.find((c) => c.key === "LLM_ACTIVE_PROVIDER")?.value as string) ||
													"openai",
											);
											setModelName(
												(configs.find((c) => c.key === "LLM_ACTIVE_MODEL_NAME")?.value as string) ||
													"",
											);
											setApiKey(
												(configs.find((c) => c.key === "LLM_API_KEY")?.value as string) || "",
											);
										}
									}}
									disabled={updateConfig.isPending || fetchModels.isPending}
								>
									Cancel
								</Button>
								
								<Button
									className="bg-blue-600 hover:bg-blue-700 text-white shadow-none px-5 rounded-lg font-medium"
									onClick={handleSave}
									disabled={updateConfig.isPending || !modelName || !apiKey}
								>
									{updateConfig.isPending ? (
										<RiLoader4Line className="size-4.5 mr-2 animate-spin" />
									) : (
										<RiCheckLine className="size-4.5 mr-2" />
									)}
									Save
								</Button>
							</>
						) : (
							<Button
								variant="outline"
								className="border-blue-500 text-blue-500 hover:text-blue-600 hover:bg-blue-50 bg-transparent shadow-none px-5 rounded-lg"
								onClick={() => setIsEditing(true)}
							>
								<RiEdit2Line className="size-4.5 mr-2" />
								Edit
							</Button>
						)}
					</div>
				</div>

				<div className="grid grid-cols-3 gap-6">
					<div className="flex flex-col gap-2">
						<span className="text-sm font-medium text-black-500">Active Provider</span>
						<Select
							value={activeProvider}
							onValueChange={(val) => {
								setActiveProvider(val ?? "");
								setAvailableModels([]);
								setModelName("");
								setApiKey("");
							}}
							disabled={!isEditing}
						>
							<SelectTrigger className={`w-full h-10 rounded-lg ${inputClass}`}>
								<SelectValue placeholder="Select provider" />
							</SelectTrigger>
							<SelectContent alignItemWithTrigger={false}>
								<SelectItem value="openai">OpenAI</SelectItem>
								<SelectItem value="deepseek">DeepSeek</SelectItem>
								<SelectItem value="gemini">Google Gemini</SelectItem>
							</SelectContent>
						</Select>
					</div>
					
					<div className="flex flex-col gap-2">
						<span className="text-sm font-medium text-black-500">API Key</span>
						<div className="relative">
							<Input
								type={showKeys ? "text" : "password"}
								disabled={!isEditing}
								value={apiKey}
								placeholder={
									activeProvider === "gemini"
										? "e.g. AIzaSy..."
										: activeProvider === "deepseek"
											? "e.g. sk-..."
											: "e.g. sk-proj-..."
								}
								onChange={(e) => {
									setApiKey(e.target.value);
									setAvailableModels([]);
									setModelName("");
								}}
								onBlur={() => {
									if (apiKey.length > 5 && availableModels.length === 0) {
										handleFetchModels();
									}
								}}
								className={`w-full h-10 rounded-lg disabled:opacity-75 pr-10 ${inputClass}`}
							/>
							<button
								type="button"
								className="absolute right-3 top-1/2 -translate-y-1/2 text-black-400 hover:text-black-600 disabled:opacity-50"
								onClick={() => setShowKeys(!showKeys)}
								disabled={!isEditing && !apiKey}
							>
								{showKeys ? <RiEyeOffLine className="size-4" /> : <RiEyeLine className="size-4" />}
							</button>
						</div>
					</div>

					<div className="flex flex-col gap-2">
						<div className="flex justify-between items-center">
							<span className="text-sm font-medium text-black-500">Active Model</span>
							{isEditing && (
								<button 
									type="button" 
									onClick={handleFetchModels}
									disabled={!apiKey || fetchModels.isPending}
									className="text-xs text-blue-600 font-medium hover:text-blue-700 disabled:opacity-50 flex items-center"
								>
									{fetchModels.isPending ? <RiLoader4Line className="size-3 mr-1 animate-spin" /> : <RiRefreshLine className="size-3 mr-1" />}
									Fetch
								</button>
							)}
						</div>
						
						{isEditing ? (
							<div className="flex flex-col gap-1">
								<Select
									value={modelName}
									onValueChange={(val) => setModelName(val ?? "")}
									disabled={availableModels.length === 0}
								>
									<SelectTrigger className={`w-full h-10 rounded-lg ${inputClass}`}>
										<SelectValue placeholder={availableModels.length > 0 ? "Select a model" : "Fetch models first"} />
									</SelectTrigger>
									<SelectContent alignItemWithTrigger={false}>
										{availableModels.map(m => (
											<SelectItem key={m.id} value={m.id}>{m.id}</SelectItem>
										))}
									</SelectContent>
								</Select>

							</div>
						) : (
							<Input
								type="text"
								disabled={true}
								value={modelName}
								className={`w-full h-10 rounded-lg disabled:opacity-75 ${inputClass}`}
							/>
						)}
					</div>
				</div>
			</div>

			<div
				className={`transition-all duration-300 ease-in-out overflow-hidden ${
					isEditing ? "opacity-100 max-h-40 mt-4" : "opacity-0 max-h-0 mt-0"
				}`}
			>
				<div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200">
					<RiInformationFill className="size-5 text-amber-500 mt-0.5 shrink-0" />
					<p className="text-sm text-amber-700 mt-0.5">
						<strong className="font-semibold text-amber-900">Note: </strong> Changes apply instantly to <strong className="font-semibold text-amber-900">new sessions</strong>. Any existing, active sessions will retain their original settings until they expire or are closed.
					</p>
				</div>
			</div>
		</div>
	);
}
