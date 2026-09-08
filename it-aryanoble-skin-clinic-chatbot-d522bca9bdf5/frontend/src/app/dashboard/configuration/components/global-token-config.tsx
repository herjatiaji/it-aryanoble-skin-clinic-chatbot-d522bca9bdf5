"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { RiCheckLine, RiEdit2Line, RiLoader4Line, RiInformationFill } from "@remixicon/react";
import * as React from "react";
import { toast } from "sonner";
import { useConfigs, useUpdateConfig } from "../hooks/use-config";

export function GlobalTokenConfig() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();

	const isGlobalLimitActive =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT_ACTIVE")?.value === "true";
	const globalTokenLimit = configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT")?.value || "1000";

	const [isActive, setIsActive] = React.useState(true);
	const [isEditing, setIsEditing] = React.useState(false);
	const [tokenAmount, setTokenAmount] = React.useState("1000");

	const [showWarning, setShowWarning] = React.useState(false);
	const warningTimeoutRef = React.useRef<NodeJS.Timeout | undefined>(undefined);

	const handleSetIsEditing = (val: boolean) => {
		setIsEditing(val);
		if (val) {
			setShowWarning(true);
			if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current);
		} else {
			setShowWarning(false);
		}
	};

	// Sync state when configs load, keeping it simple
	React.useEffect(() => {
		if (configs) {
			// Use setTimeout to avoid synchronous setState during render phase warning in React 19 / strict mode
			setTimeout(() => {
				setIsActive(isGlobalLimitActive);
				setTokenAmount(globalTokenLimit);
			}, 0);
		}
	}, [configs, isGlobalLimitActive, globalTokenLimit]);

	const handleSave = () => {
		updateConfig.mutate(
			{ key: "GLOBAL_TOKEN_LIMIT", data: { value: tokenAmount } },
			{
				onSuccess: () => {
					handleSetIsEditing(false);
					toast.success("Global token limit updated successfully!");
				},
			},
		);
	};

	const handleToggle = (checked: boolean) => {
		setIsActive(checked);

		// Show warning briefly when toggled
		setShowWarning(true);
		if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current);
		warningTimeoutRef.current = setTimeout(() => {
			// Don't hide it if we are currently editing the amount
			setShowWarning((prev) => {
				if (!isEditing) return false;
				return prev;
			});
		}, 5000);

		updateConfig.mutate(
			{ key: "GLOBAL_TOKEN_LIMIT_ACTIVE", data: { value: checked.toString() } },
			{
				onSuccess: () => {
					toast.success(`Global token limit ${checked ? "activated" : "deactivated"}!`);
				},
			}
		);
	};

	if (isLoading) {
		return <div className="p-4 text-center text-sm text-gray-500">Loading configuration...</div>;
	}

	return (
		<div className="flex flex-col w-full">
			<div className="flex flex-col gap-6 border border-black-50 rounded-lg p-4 bg-white">
				{/* Top Part: Title and Toggle */}
				<div className="flex flex-col gap-4">
					<div className="flex flex-col gap-1">
						<h3 className="text-base font-medium text-black-500">Global Token Configuration</h3>
						<p className="text-sm text-black-300">
							Apply the same token limit to all branches at once or one by one by switching the
							toggle.
						</p>
					</div>
					<div className="flex items-center gap-2">
						<Switch
							checked={isActive}
							onCheckedChange={handleToggle}
							disabled={updateConfig.isPending}
							className="data-[state=checked]:bg-blue-500"
						/>
						<span className="text-sm text-black-300">
							{isActive ? "Deactivate the configuration" : "Activate the configuration"}
						</span>
					</div>
				</div>

				{/* Bottom Part: Token Amount */}
				{isActive && (
					<div className="flex flex-col gap-6.5 border-t border-black-50 pt-6 mt-2">
						<div className="flex flex-col gap-1.5">
							<h4 className="text-base font-medium text-black-500">Token Amount (per month)</h4>
							<p className="text-sm text-black-300">
								The token is represented by the conversations held in the chatbot, and it will be
								calculated on a monthly basis.
							</p>
						</div>

						<div className="flex items-center gap-4">
							<div className="flex flex-col gap-2">
								<span className="text-sm text-black-300">Token Amount (per month)</span>
								<div className="relative">
									<Input
										type="number"
										disabled={!isEditing}
										value={tokenAmount}
										onChange={(e) => setTokenAmount(e.target.value)}
										className="w-60 bg-black-50 border-black-50 text-black-500 h-10 rounded-lg [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none disabled:opacity-75"
									/>
									<span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-black-200 pointer-events-none">
										per month
									</span>
								</div>
							</div>
							<div className="flex items-end h-17">
								{isEditing ? (
									<div className="flex items-center gap-2">
										<Button
											variant="ghost"
											className="text-black-500 hover:text-black-600 hover:bg-zinc-100 px-5 rounded-lg font-medium"
											onClick={() => {
												handleSetIsEditing(false);
												setTokenAmount(globalTokenLimit);
											}}
											disabled={updateConfig.isPending}
										>
											Cancel
										</Button>
										<Button
											className="bg-blue-600 hover:bg-blue-700 text-white shadow-none px-5 rounded-lg font-medium"
											onClick={handleSave}
											disabled={updateConfig.isPending}
										>
											{updateConfig.isPending ? (
												<RiLoader4Line className="size-4.5 mr-2 animate-spin" />
											) : (
												<RiCheckLine className="size-4.5 mr-2" />
											)}
											Save and Apply
										</Button>
									</div>
								) : (
									<Button
										variant="outline"
										className="border-blue-500 text-blue-500 hover:text-blue-600 hover:bg-blue-50 bg-transparent shadow-none px-5 rounded-lg"
										onClick={() => handleSetIsEditing(true)}
										disabled={!isActive}
									>
										<RiEdit2Line className="size-4.5 mr-2" />
										Edit
									</Button>
								)}
							</div>
						</div>
					</div>
				)}
			</div>

			<div
				className={`transition-all duration-300 ease-in-out overflow-hidden ${
					showWarning ? "opacity-100 max-h-40 mt-4" : "opacity-0 max-h-0 mt-0"
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
