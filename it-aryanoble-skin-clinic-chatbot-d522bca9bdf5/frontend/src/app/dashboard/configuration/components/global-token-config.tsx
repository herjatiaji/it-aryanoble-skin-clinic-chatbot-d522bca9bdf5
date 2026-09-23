"use client";

import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { Switch } from "@/components/ui/switch";
import { RiInformationFill } from "@remixicon/react";
import { useTokenConfigState } from "../hooks/use-token-config-state";
import { ConfigCardSkeleton } from "./skeletons/config-card-skeleton";
import { TokenLimitRow } from "./token-limit-row";

export function GlobalTokenConfig() {
	const {
		isLoading,
		isPending,
		isActive,
		isThresholdActive,
		isBranchActive,
		isSpdveActive,
		isGpPlusActive,
		thresholdAmount,
		setThresholdAmount,
		globalThreshold,
		editingThreshold,
		setEditingThreshold,
		branchAmount,
		setBranchAmount,
		branchTokenLimit,
		editingBranch,
		setEditingBranch,
		spdveAmount,
		setSpdveAmount,
		spdveLimit,
		editingSpdve,
		setEditingSpdve,
		gpPlusAmount,
		setGpPlusAmount,
		gpPlusLimit,
		editingGpPlus,
		setEditingGpPlus,
		savingKey,
		deactivatingKey,
		showWarning,
		toggleModalOpen,
		setToggleModalOpen,
		pendingToggleActive,
		setPendingToggleActive,
		saveModalOpen,
		setSaveModalOpen,
		pendingSave,
		setPendingSave,
		deactivateModalOpen,
		setDeactivateModalOpen,
		pendingDeactivate,
		setPendingDeactivate,
		handleInitiateToggle,
		handleConfirmToggle,
		handleInitiateSave,
		handleConfirmSave,
		handleInitiateDeactivate,
		handleConfirmDeactivate,
	} = useTokenConfigState();

	if (isLoading) {
		return <ConfigCardSkeleton lines={3} />;
	}

	return (
		<div className="flex flex-col w-full">
			<div className="flex flex-col gap-6 border border-gray-100 rounded-lg p-4 bg-white">
				{/* Top Part: Title and Toggle */}
				<div className="flex flex-col gap-4">
					<div className="flex flex-col gap-1">
						<h3 className="text-base font-medium text-zinc-900">Global Token Configuration</h3>
						<p className="text-sm text-zinc-500">
							Apply the same token limit to all branches at once or one by one by switching the
							toggle.
						</p>
					</div>
					<div className="flex items-center gap-2">
						<Switch
							id="global-token-config-switch"
							checked={isActive}
							onCheckedChange={handleInitiateToggle}
							disabled={isPending}
							className="data-[state=checked]:bg-blue-500 cursor-pointer"
						/>
						<label
							htmlFor="global-token-config-switch"
							className="text-sm text-zinc-600 cursor-pointer select-none"
						>
							{isActive ? "Deactivate the configuration" : "Activate the configuration"}
						</label>
					</div>
				</div>

				{/* Active Configuration Content */}
				{isActive && (
					<div className="flex flex-col gap-6 border-t border-gray-100 pt-6">
						{/* 1. Global Token Threshold */}
						<div className="flex flex-col gap-3">
							<h4 className="text-base font-medium text-zinc-900">
								Global Token Threshold (per month)
							</h4>
							<TokenLimitRow
								label="Global Token Threshold"
								value={thresholdAmount}
								onChange={setThresholdAmount}
								isEditing={editingThreshold}
								isActive={isThresholdActive}
								onEdit={() => setEditingThreshold(true)}
								onCancel={() => {
									setEditingThreshold(false);
									setThresholdAmount(globalThreshold);
								}}
								onSave={() =>
									handleInitiateSave(
										"GLOBAL_TOKEN_THRESHOLD",
										"Save Global Token Threshold",
										`Are you sure you want to update the global token threshold to ${Number(thresholdAmount || 0).toLocaleString()} tokens per month?`,
										thresholdAmount,
										setEditingThreshold,
									)
								}
								isSaving={savingKey === "GLOBAL_TOKEN_THRESHOLD"}
								placeholder="1,000,000"
							/>
						</div>

						{/* 2. Token Amount (per month) Section */}
						<div className="flex flex-col gap-6 border-t border-gray-100 pt-5">
							<div className="flex flex-col gap-1">
								<h4 className="text-base font-medium text-zinc-900">Token Amount (per month)</h4>
								<p className="text-sm text-zinc-500">
									The token is represented by the conversations held in the chatbot, and it will be
									calculated on a monthly basis.
								</p>
							</div>

							{/* Token Amount (per Branch) */}
							<TokenLimitRow
								label="Token Amount (per Branch)"
								value={branchAmount}
								onChange={setBranchAmount}
								isEditing={editingBranch}
								isActive={isBranchActive}
								onEdit={() => setEditingBranch(true)}
								onCancel={() => {
									setEditingBranch(false);
									setBranchAmount(branchTokenLimit);
								}}
								onSave={() =>
									handleInitiateSave(
										"GLOBAL_TOKEN_LIMIT",
										"Save Branch Token Limit",
										`Are you sure you want to update the token amount per branch to ${Number(branchAmount || 0).toLocaleString()} tokens per month?`,
										branchAmount,
										setEditingBranch,
									)
								}
								onDeactivate={() =>
									handleInitiateDeactivate(
										"GLOBAL_TOKEN_LIMIT",
										"Deactivate Shared Branch Token Limit",
										"Are you sure you want to deactivate the Shared Branch Token Limit? All branches will immediately revert to their individual branch token limits.",
									)
								}
								isSaving={savingKey === "GLOBAL_TOKEN_LIMIT"}
								isDeactivating={deactivatingKey === "GLOBAL_TOKEN_LIMIT"}
								placeholder="3,000,000"
							/>

							{/* Row: Token Amount (SpDVE) & Token Amount (GP Plus) */}
							<div className="flex flex-wrap items-start gap-8">
								<TokenLimitRow
									label="Token Amount (SpDVE)"
									value={spdveAmount}
									onChange={setSpdveAmount}
									isEditing={editingSpdve}
									isActive={isSpdveActive}
									onEdit={() => setEditingSpdve(true)}
									onCancel={() => {
										setEditingSpdve(false);
										setSpdveAmount(spdveLimit);
									}}
									onSave={() =>
										handleInitiateSave(
											"TOKEN_LIMIT_SPKK",
											"Save SpDVE Token Limit",
											`Are you sure you want to update the token amount for SpDVE to ${Number(spdveAmount || 0).toLocaleString()} tokens per month?`,
											spdveAmount,
											setEditingSpdve,
										)
									}
									onDeactivate={() =>
										handleInitiateDeactivate(
											"TOKEN_LIMIT_SPKK",
											"Deactivate SpDVE Token Limit",
											"Are you sure you want to deactivate the SpDVE global token quota? SpDVE doctors will revert to drawing from branch pools or individual custom limits.",
										)
									}
									isSaving={savingKey === "TOKEN_LIMIT_SPKK"}
									isDeactivating={deactivatingKey === "TOKEN_LIMIT_SPKK"}
									placeholder="500,000"
								/>

								<TokenLimitRow
									label="Token Amount (GP Plus)"
									value={gpPlusAmount}
									onChange={setGpPlusAmount}
									isEditing={editingGpPlus}
									isActive={isGpPlusActive}
									onEdit={() => setEditingGpPlus(true)}
									onCancel={() => {
										setEditingGpPlus(false);
										setGpPlusAmount(gpPlusLimit);
									}}
									onSave={() =>
										handleInitiateSave(
											"TOKEN_LIMIT_GP",
											"Save GP Plus Token Limit",
											`Are you sure you want to update the token amount for GP Plus to ${Number(gpPlusAmount || 0).toLocaleString()} tokens per month?`,
											gpPlusAmount,
											setEditingGpPlus,
										)
									}
									onDeactivate={() =>
										handleInitiateDeactivate(
											"TOKEN_LIMIT_GP",
											"Deactivate GP Plus Token Limit",
											"Are you sure you want to deactivate the GP Plus global token quota? GP Plus doctors will revert to drawing from branch pools or individual custom limits.",
										)
									}
									isSaving={savingKey === "TOKEN_LIMIT_GP"}
									isDeactivating={deactivatingKey === "TOKEN_LIMIT_GP"}
									placeholder="250,000"
								/>
							</div>
						</div>
					</div>
				)}
			</div>

			{/* Informational Toast / Banner */}
			<div
				className={`transition-all duration-300 ease-in-out overflow-hidden ${
					showWarning ? "opacity-100 max-h-40 mt-4" : "opacity-0 max-h-0 mt-0"
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

			{/* Toggle Confirmation Modal */}
			<ConfirmationModal
				isOpen={toggleModalOpen}
				onOpenChange={(open) => {
					setToggleModalOpen(open);
					if (!open) setPendingToggleActive(null);
				}}
				title={
					pendingToggleActive
						? "Activate Global Token Configuration"
						: "Deactivate Global Token Configuration"
				}
				description={
					pendingToggleActive
						? "Are you sure you want to activate the global token limit configuration for all branches?"
						: "Are you sure you want to deactivate the global token limit configuration?"
				}
				confirmText={pendingToggleActive ? "Activate" : "Deactivate"}
				variant={pendingToggleActive ? "primary" : "destructive"}
				isLoading={isPending}
				onConfirm={handleConfirmToggle}
			/>

			{/* Save Field Confirmation Modal */}
			<ConfirmationModal
				isOpen={saveModalOpen}
				onOpenChange={(open) => {
					setSaveModalOpen(open);
					if (!open) setPendingSave(null);
				}}
				title={pendingSave?.title || "Save Configuration"}
				description={pendingSave?.description || "Are you sure you want to save these changes?"}
				confirmText="Save and Apply"
				isLoading={isPending && savingKey !== null}
				onConfirm={handleConfirmSave}
			/>

			{/* Deactivate Field Confirmation Modal */}
			<ConfirmationModal
				isOpen={deactivateModalOpen}
				onOpenChange={(open) => {
					setDeactivateModalOpen(open);
					if (!open) setPendingDeactivate(null);
				}}
				title={pendingDeactivate?.title || "Deactivate Configuration Rule"}
				description={
					pendingDeactivate?.description ||
					"Are you sure you want to deactivate this configuration rule?"
				}
				confirmText="Deactivate"
				variant="destructive"
				isLoading={isPending && deactivatingKey !== null}
				onConfirm={handleConfirmDeactivate}
			/>
		</div>
	);
}
