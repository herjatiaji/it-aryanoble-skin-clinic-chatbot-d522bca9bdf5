"use client";

import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RiCheckLine, RiEdit2Line, RiInformationFill, RiLoader4Line } from "@remixicon/react";
import { useTimeLimitState } from "../hooks/use-time-limit-state";
import { ConfigCardSkeleton } from "./skeletons/config-card-skeleton";

export function GlobalTimeLimitConfig() {
	const {
		isLoading,
		isPending,
		isEditing,
		setIsEditing,
		timeAmount,
		setTimeAmount,
		isConfirmOpen,
		setIsConfirmOpen,
		handleCancel,
		handleConfirmSave,
	} = useTimeLimitState();

	if (isLoading) {
		return <ConfigCardSkeleton lines={1} />;
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
									min={1}
									disabled={!isEditing}
									value={timeAmount}
									onChange={(e) => setTimeAmount(e.target.value)}
									onWheel={(e) => (e.target as HTMLInputElement).blur()}
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
										type="button"
										variant="outline"
										className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 font-medium h-10 text-sm transition-colors cursor-pointer shadow-none"
										onClick={handleCancel}
										disabled={isPending}
									>
										Cancel
									</Button>
									<Button
										type="button"
										className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 font-medium h-10 text-sm transition-colors cursor-pointer shadow-none gap-1.5 disabled:opacity-50"
										onClick={() => setIsConfirmOpen(true)}
										disabled={isPending || !timeAmount}
									>
										{isPending ? (
											<RiLoader4Line className="size-4 animate-spin mr-1" />
										) : (
											<RiCheckLine className="size-4 mr-1" />
										)}
										Save
									</Button>
								</div>
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
						<strong className="font-semibold text-amber-900">Note: </strong> Changes apply instantly
						to <strong className="font-semibold text-amber-900">new sessions</strong>. Any existing,
						active sessions will retain their original settings until they expire or are closed.
					</p>
				</div>
			</div>

			<ConfirmationModal
				isOpen={isConfirmOpen}
				onOpenChange={setIsConfirmOpen}
				title="Save Time Limit Per Session"
				description={`Are you sure you want to update the session time limit to ${timeAmount} minutes per session?`}
				confirmText="Save and Apply"
				isLoading={isPending}
				onConfirm={handleConfirmSave}
			/>
		</div>
	);
}
