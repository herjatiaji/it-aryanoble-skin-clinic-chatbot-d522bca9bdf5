"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RiCheckLine, RiEdit2Line, RiLoader4Line, RiInformationFill } from "@remixicon/react";
import * as React from "react";
import { toast } from "sonner";
import { useConfigs, useUpdateConfig } from "../hooks/use-config";

export function GlobalTimeLimitConfig() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();

	const timeLimit = configs?.find((c) => c.key === "TIME_LIMIT_PER_SESSION")?.value || "5";

	const [isEditing, setIsEditing] = React.useState(false);
	const [timeAmount, setTimeAmount] = React.useState("5");

	// Sync state when configs load, keeping it simple
	React.useEffect(() => {
		if (configs) {
			// Use setTimeout to avoid synchronous setState during render phase warning in React 19 / strict mode
			setTimeout(() => {
				setTimeAmount(timeLimit);
			}, 0);
		}
	}, [configs, timeLimit]);

	const handleSave = () => {
		updateConfig.mutate(
			{ key: "TIME_LIMIT_PER_SESSION", data: { value: timeAmount } },
			{
				onSuccess: () => {
					setIsEditing(false);
					toast.success("Time limit per session updated successfully!");
				},
			},
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
						<h4 className="text-base font-medium text-black-500">Time Limit Per Session</h4>
						<p className="text-sm text-black-300">
							the time that already set up is for end each session
						</p>
					</div>

					<div className="flex items-center gap-4">
						<div className="flex flex-col gap-2">
							<span className="text-sm text-black-300">Time</span>
							<div className="relative">
								<Input
									type="number"
									disabled={!isEditing}
									value={timeAmount}
									onChange={(e) => setTimeAmount(e.target.value)}
									className="w-60 bg-black-50 border-black-50 text-black-500 h-10 rounded-lg [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none disabled:opacity-75"
								/>
								<span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-black-200 pointer-events-none">
									minutes /session
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
											setIsEditing(false);
											setTimeAmount(timeLimit);
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
									onClick={() => setIsEditing(true)}
								>
									<RiEdit2Line className="size-4.5 mr-2" />
									Edit
								</Button>
							)}
						</div>
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
