"use client";

import { TokenInput } from "@/components/shared/token-input";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { RiCheckLine, RiInformationLine, RiLoader4Line } from "@remixicon/react";
import { useEffect, useState } from "react";
import { useConfigs } from "../../configuration/hooks/use-config";
import { UserResponse } from "../api/types";
import { useUpdateDoctorAccess } from "../hooks/use-users";

export function DoctorAdjustLimitDialog({
	isOpen,
	onOpenChange,
	doctor,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	doctor: UserResponse | null;
}) {
	const { data: configs } = useConfigs();
	const isMasterActive =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT_ACTIVE")?.value === "true";
	const isBranchGlobalActive =
		isMasterActive &&
		configs?.find((c) => c.key === "GLOBAL_BRANCH_LIMIT_ACTIVE")?.value === "true";
	const isSpdveGlobalActive =
		isMasterActive && configs?.find((c) => c.key === "GLOBAL_SPKK_LIMIT_ACTIVE")?.value === "true";
	const isGpGlobalActive =
		isMasterActive && configs?.find((c) => c.key === "GLOBAL_GP_LIMIT_ACTIVE")?.value === "true";

	const globalBranchLimit =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT")?.value || "3000000";
	const spdveLimit = configs?.find((c) => c.key === "TOKEN_LIMIT_SPKK")?.value || "500000";
	const gpPlusLimit = configs?.find((c) => c.key === "TOKEN_LIMIT_GP")?.value || "250000";

	const drTypeUpper = (doctor?.dr_type || "").toUpperCase();
	const isSpDVE =
		drTypeUpper.includes("SPKK") || drTypeUpper.includes("SPDVE") || drTypeUpper.includes("SPDV");
	const isGP = drTypeUpper.includes("GP") || drTypeUpper.includes("UMUM");
	const isDoctorTypeGlobalActive = isSpDVE ? isSpdveGlobalActive : isGP ? isGpGlobalActive : false;
	const effectiveGlobalLimit = isSpDVE ? Number(spdveLimit) : isGP ? Number(gpPlusLimit) : 0;

	// Determine branch token limit bounds
	const branches = doctor?.branches || [];
	const rawMaxBranchLimit =
		branches.length > 0
			? Math.max(
					...branches.map((b) =>
						b.has_custom_limit
							? b.token_limit ?? 0
							: isBranchGlobalActive
							? Number(globalBranchLimit)
							: b.token_limit ?? 0,
					),
				)
			: 0;

	const maxBranchLimit = rawMaxBranchLimit;

	const hasCustomLimit =
		doctor?.token_limit !== null && doctor?.token_limit !== undefined && doctor.token_limit > 0;
	const currentEffectiveLimit = hasCustomLimit
		? doctor.token_limit!
		: isDoctorTypeGlobalActive
			? effectiveGlobalLimit
			: maxBranchLimit;

	const tokensUsed = doctor?.tokens_used ?? 0;
	const tokensLeft = Math.max(0, currentEffectiveLimit - tokensUsed);

	const isNoBranchAssigned = branches.length === 0;
	const isBranchLimitUnset = isNoBranchAssigned || (!isBranchGlobalActive && maxBranchLimit === 0);

	const [newLimit, setNewLimit] = useState<number>(0);
	const updateDoctorAccess = useUpdateDoctorAccess();

	useEffect(() => {
		if (isOpen && doctor) {
			setTimeout(() => {
				setNewLimit(doctor.token_limit ?? (isDoctorTypeGlobalActive ? effectiveGlobalLimit : 0));
			}, 0);
		}
	}, [isOpen, doctor, isDoctorTypeGlobalActive, effectiveGlobalLimit]);

	const isExceedingBranch = newLimit > maxBranchLimit && !isBranchLimitUnset;
	const isNegativeLimit = newLimit < 0;

	const handleSave = () => {
		if (!doctor?.id || isBranchLimitUnset || isExceedingBranch || isNegativeLimit) return;

		updateDoctorAccess.mutate(
			{ userId: doctor.id, data: { token_limit: newLimit } },
			{
				onSuccess: () => {
					onOpenChange(false);
				},
			},
		);
	};

	return (
		<Dialog
			open={isOpen}
			onOpenChange={(open) => {
				if (!open && !updateDoctorAccess.isPending) {
					onOpenChange(open);
				} else if (open) {
					onOpenChange(open);
				}
			}}
		>
			<DialogContent className="sm:max-w-md p-0 flex flex-col gap-0 rounded-lg overflow-hidden bg-white border border-gray-200 shadow-none">
				<DialogHeader className="p-4 border-b border-gray-100 flex flex-row items-center justify-between">
					<DialogTitle className="text-base font-semibold text-foreground">
						Adjust Token Limit
					</DialogTitle>
					<DialogDescription className="sr-only">
						Adjust individual doctor monthly token limit
					</DialogDescription>
				</DialogHeader>

				<div className="p-4 flex flex-col gap-4">
					{/* Branch Context Info */}
					<div className="flex flex-col gap-1 text-sm bg-gray-50 p-3 rounded-lg border border-gray-100">
						<span className="font-medium text-gray-700">Assigned Branch Limit:</span>
						{branches.length > 0 ? (
							branches.map((b) => (
								<span key={b.id} className="text-gray-600 text-xs">
									• {b.name}:{" "}
									{b.has_custom_limit
										? `${(b.token_limit ?? 0).toLocaleString()} tokens (Custom Override)`
										: isBranchGlobalActive
										? `${Number(globalBranchLimit).toLocaleString()} tokens (Global Pool)`
										: b.token_limit
											? `${b.token_limit.toLocaleString()} tokens`
											: "Not set (0)"}
								</span>
							))
						) : (
							<span className="text-xs text-amber-600">No branch assigned yet</span>
						)}
					</div>

					<div className="flex flex-col gap-1 text-sm text-foreground">
						<span>
							Current doctor limit: {currentEffectiveLimit.toLocaleString()}{" "}
							{isDoctorTypeGlobalActive && (
								<span className="text-xs text-blue-600">
									({hasCustomLimit ? "Custom Override" : "Global Default"})
								</span>
							)}
						</span>
						<span>Remaining: {tokensLeft.toLocaleString()}</span>
						<span>Used: {tokensUsed.toLocaleString()}</span>
					</div>

					{isBranchLimitUnset ? (
						<div className="bg-amber-50 border border-amber-500 rounded-lg p-4 text-sm text-amber-800 flex gap-2">
							<RiInformationLine className="h-5 w-5 shrink-0 text-amber-600" />
							<span>
								{isNoBranchAssigned
									? "Doctor must be assigned to at least one branch before adjusting token limit."
									: "Branch token limit must be set on the Branches menu first before adjusting doctor token limits."}
							</span>
						</div>
					) : (
						<>
							<div className="flex flex-col gap-2">
								<span className="text-xs font-medium text-zinc-700">
									{isDoctorTypeGlobalActive ? "Custom Token Limit (Override)" : "New Token Limit"}
								</span>
								<TokenInput
									id="doctor_token_limit"
									value={newLimit}
									onChange={(val) => setNewLimit(val)}
									suffix="tokens"
									previewSuffix="tokens / month"
									min={0}
								/>
								{isExceedingBranch && (
									<span className="text-xs text-red-600">
										Doctor limit cannot exceed branch limit ({maxBranchLimit.toLocaleString()}{" "}
										tokens).
									</span>
								)}
							</div>

							<div className="bg-blue-50 border border-blue-600 rounded-lg p-4 text-sm text-blue-600 flex gap-2">
								<RiInformationLine className="h-5 w-5 shrink-0" />
								<span>
									We recommend not setting the token limit below the used token amount (
									{tokensUsed.toLocaleString()}).
								</span>
							</div>
						</>
					)}
				</div>

				<div className="p-4 border-t border-gray-100 flex items-center justify-end gap-2 bg-zinc-50/50">
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={updateDoctorAccess.isPending}
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
					>
						Cancel
					</Button>
					<Button
						className="bg-blue-600 text-white hover:bg-blue-700 px-4 h-10 rounded-lg font-medium text-sm transition-colors cursor-pointer shadow-none disabled:opacity-50"
						onClick={handleSave}
						disabled={updateDoctorAccess.isPending || isBranchLimitUnset || isExceedingBranch}
					>
						{updateDoctorAccess.isPending ? (
							<RiLoader4Line className="mr-2 h-4 w-4 animate-spin" />
						) : (
							<RiCheckLine className="mr-2 h-4 w-4" />
						)}
						Save Changes
					</Button>
				</div>
			</DialogContent>
		</Dialog>
	);
}
