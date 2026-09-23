"use client";

import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	RiCheckLine,
	RiEdit2Line,
	RiEyeLine,
	RiEyeOffLine,
	RiInformationFill,
	RiLoader4Line,
	RiRefreshLine,
} from "@remixicon/react";
import { useModelConfigState } from "../hooks/use-model-config-state";
import { ConfigCardSkeleton } from "./skeletons/config-card-skeleton";

export function GlobalModelConfig() {
	const {
		isLoading,
		isUpdating,
		isFetchingModels,
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
	} = useModelConfigState();

	if (isLoading) {
		return <ConfigCardSkeleton lines={2} />;
	}

	return (
		<div className="flex flex-col w-full">
			<div className="flex flex-col gap-6 border border-gray-100 rounded-lg p-4 bg-white">
				{/* Top Part: Title and Edit Button */}
				<div className="flex justify-between items-start">
					<div className="flex flex-col gap-1">
						<h3 className="text-base font-medium text-zinc-900">Global AI Model Configuration</h3>
						<p className="text-sm text-zinc-500">
							Configure the default LLM provider, active model, and API key for the chatbot.
						</p>
					</div>
					<div className="flex items-center gap-2">
						{isEditing ? (
							<>
								<Button
									type="button"
									variant="outline"
									className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
									onClick={handleCancel}
									disabled={isUpdating || isFetchingModels}
								>
									Cancel
								</Button>

								<Button
									type="button"
									className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none gap-1.5 disabled:opacity-50"
									onClick={handleInitiateSave}
									disabled={isUpdating || !modelName || !apiKey}
								>
									{isUpdating ? (
										<RiLoader4Line className="size-4 animate-spin mr-1" />
									) : (
										<RiCheckLine className="size-4 mr-1" />
									)}
									Save
								</Button>
							</>
						) : (
							<Button
								type="button"
								variant="outline"
								className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 text-sm font-medium transition-colors cursor-pointer shadow-none gap-1.5"
								onClick={() => setIsEditing(true)}
							>
								<RiEdit2Line className="size-4 text-zinc-500" />
								Edit
							</Button>
						)}
					</div>
				</div>

				<div className="grid grid-cols-1 md:grid-cols-3 gap-6">
					{/* Active Provider */}
					<Field className="gap-2">
						<FieldLabel className="text-sm font-medium text-zinc-800">Active Provider</FieldLabel>
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
							<SelectTrigger className="w-full h-10 rounded-lg bg-zinc-50 border-gray-200 text-zinc-800">
								<SelectValue placeholder="Select provider" />
							</SelectTrigger>
							<SelectContent alignItemWithTrigger={false} className="bg-white">
								<SelectItem value="openai">OpenAI</SelectItem>
								<SelectItem value="deepseek">DeepSeek</SelectItem>
								<SelectItem value="gemini">Google Gemini</SelectItem>
							</SelectContent>
						</Select>
					</Field>

					{/* API Key */}
					<Field className="gap-2">
						<FieldLabel className="text-sm font-medium text-zinc-800">API Key</FieldLabel>
						<div className="relative">
							<Input
								type={showKeys ? "text" : "password"}
								disabled={!isEditing}
								value={apiKey}
								autoComplete="off"
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
								className="w-full h-10 rounded-lg disabled:opacity-75 pr-10 bg-zinc-50 border-gray-200 text-zinc-800 focus-visible:ring-blue-500"
							/>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								className="absolute right-1 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 size-8 cursor-pointer"
								onClick={() => setShowKeys(!showKeys)}
								disabled={!isEditing && !apiKey}
							>
								{showKeys ? <RiEyeOffLine className="size-4" /> : <RiEyeLine className="size-4" />}
							</Button>
						</div>
					</Field>

					{/* Active Model */}
					<Field className="gap-2">
						<div className="flex justify-between items-center">
							<FieldLabel className="text-sm font-medium text-zinc-800">Active Model</FieldLabel>
							{isEditing && (
								<Button
									type="button"
									variant="ghost"
									size="xs"
									onClick={handleFetchModels}
									disabled={!apiKey || isFetchingModels}
									className="text-xs text-blue-600 font-medium hover:text-blue-700 disabled:opacity-50 flex items-center h-auto p-0 cursor-pointer"
								>
									{isFetchingModels ? (
										<RiLoader4Line className="size-3 mr-1 animate-spin" />
									) : (
										<RiRefreshLine className="size-3 mr-1" />
									)}
									Fetch
								</Button>
							)}
						</div>

						{isEditing ? (
							<Select
								value={modelName}
								onValueChange={(val) => setModelName(val ?? "")}
								disabled={availableModels.length === 0}
							>
								<SelectTrigger className="w-full h-10 rounded-lg bg-zinc-50 border-gray-200 text-zinc-800">
									<SelectValue
										placeholder={
											availableModels.length > 0 ? "Select a model" : "Fetch models first"
										}
									/>
								</SelectTrigger>
								<SelectContent alignItemWithTrigger={false} className="bg-white">
									{availableModels.map((m) => (
										<SelectItem key={m.id} value={m.id}>
											{m.id}
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						) : (
							<Input
								type="text"
								disabled={true}
								value={modelName}
								className="w-full h-10 rounded-lg disabled:opacity-75 bg-zinc-50 border-gray-200 text-zinc-800"
							/>
						)}
					</Field>
				</div>
			</div>

			{/* Info Banner */}
			<div
				className={`transition-all duration-300 ease-in-out overflow-hidden ${
					isEditing ? "opacity-100 max-h-40 mt-4" : "opacity-0 max-h-0 mt-0"
				}`}
			>
				<div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200">
					<RiInformationFill className="size-5 text-amber-500 mt-0.5 shrink-0" />
					<p className="text-sm text-amber-700 mt-0.5">
						<strong className="font-semibold text-amber-900">Note: </strong> Changes apply instantly
						to <strong className="font-semibold text-amber-900">new sessions</strong>. Any existing,
						active sessions will retain their original settings until they expire or are closed.
					</p>
				</div>
			</div>

			<ConfirmationModal
				isOpen={isConfirmOpen}
				onOpenChange={setIsConfirmOpen}
				title="Save AI Model Configuration"
				description={`Are you sure you want to update the AI model settings with provider "${activeProvider}" and model "${modelName}"?`}
				confirmText="Save and Apply"
				isLoading={isUpdating}
				onConfirm={handleSave}
			/>
		</div>
	);
}
