"use client";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RiEyeLine } from "@remixicon/react";
import * as React from "react";
import { useConfigs } from "../../configuration/hooks/use-config";
import { BranchResponse } from "../api/types";
import { EditBranchTokenDialog } from "./edit-branch-token-dialog";

interface ViewBranchSheetProps {
	branch: BranchResponse;
}

export function ViewBranchSheet({ branch }: ViewBranchSheetProps) {
	const [open, setOpen] = React.useState(false);

	const { data: configs } = useConfigs();
	const isMasterActive =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT_ACTIVE")?.value === "true";
	const isBranchGlobalActive =
		configs?.find((c) => c.key === "GLOBAL_BRANCH_LIMIT_ACTIVE")?.value === "true";
	const isGlobalLimitActive = isMasterActive && isBranchGlobalActive;

	const globalBranchLimit =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT")?.value || "3000000";

	const hasCustomLimit = branch.has_custom_limit ?? false;

	const effectiveBranchLimit = hasCustomLimit
		? (branch.token_limit ?? 0)
		: isGlobalLimitActive
		? Number(globalBranchLimit)
		: (branch.token_limit ?? branch.tokensMonth ?? 0);

	const branchUsed = branch.used ?? 0;
	const branchRemaining = Math.max(0, effectiveBranchLimit - branchUsed);

	return (
		<>
			<Button
				variant="outline"
				className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-3 h-8 font-medium text-xs transition-colors cursor-pointer shadow-none gap-1.5"
				onClick={() => setOpen(true)}
			>
				<RiEyeLine className="size-3.5 shrink-0" />
				View
			</Button>
			<Sheet open={open} onOpenChange={setOpen}>
				<SheetContent className="sm:max-w-100 w-full p-0 flex flex-col gap-0 border-l border-gray-200 bg-white">
					<SheetHeader className="p-4 border-b border-gray-200">
						<SheetTitle className="text-base font-medium text-black-500 text-left">
							Branch Information
						</SheetTitle>
					</SheetHeader>

					<div className="flex-1 overflow-y-auto pb-6">
						<Tabs defaultValue="information" className="w-full">
							<div className="px-6 pt-4">
								<TabsList
									variant="line"
									className="w-full justify-start h-auto p-0 bg-transparent gap-6"
								>
									<TabsTrigger
										value="information"
										className="font-medium text-sm text-zinc-600 hover:text-blue-700 data-active:text-blue-700 data-active:after:bg-blue-700 px-0 pb-2 cursor-pointer"
									>
										Branch Information
									</TabsTrigger>
									<TabsTrigger
										value="doctors"
										className="font-medium text-sm text-zinc-600 hover:text-blue-700 data-active:text-blue-700 data-active:after:bg-blue-700 px-0 pb-2 cursor-pointer"
									>
										Doctor List
									</TabsTrigger>
								</TabsList>
							</div>

							<TabsContent value="information" className="p-6 m-0 flex flex-col gap-6">
								{/* Details */}
								<div className="flex flex-col gap-1">
									<span className="text-sm text-black-300">Name</span>
									<span className="text-sm font-medium text-black-500">{branch.name}</span>
								</div>

								{branch.code && (
									<div className="flex flex-col gap-1">
										<span className="text-sm text-black-300">Branch Code</span>
										<span className="text-sm font-medium text-black-500">{branch.code}</span>
									</div>
								)}

								{branch.ecosystem && (
									<div className="flex flex-col gap-1">
										<span className="text-sm text-black-300">Ecosystem</span>
										<span className="text-sm font-medium text-black-500">{branch.ecosystem}</span>
									</div>
								)}

								<div className="flex items-start justify-between gap-4">
									<div className="flex flex-col gap-1">
										<span className="text-sm text-black-300">Tokens</span>
										<span className="text-sm font-medium text-blue-600">
											{effectiveBranchLimit.toLocaleString()}{" "}
											<span className="text-black-500 font-normal">/month</span>
										</span>
										{hasCustomLimit ? (
											<div className="pt-0.5">
												{effectiveBranchLimit === 0 ? (
													<span className="inline-flex items-center text-[11px] bg-red-50 text-red-700 px-2 py-0.5 rounded-md font-medium border border-red-200">
														Custom Override (Blocked: 0)
													</span>
												) : (
													<span className="inline-flex items-center text-[11px] bg-amber-50 text-amber-700 px-2 py-0.5 rounded-md font-medium border border-amber-200">
														Custom Override
													</span>
												)}
											</div>
										) : isGlobalLimitActive ? (
											<div className="pt-0.5">
												<span className="inline-flex items-center text-[11px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-md font-medium border border-blue-100">
													Global Pool
												</span>
											</div>
										) : null}
									</div>
									<EditBranchTokenDialog branch={branch} />
								</div>

								<div className="flex items-center gap-4">
									<div className="flex flex-col gap-1 flex-1">
										<span className="text-sm text-black-300">Used</span>
										<span className="text-sm font-medium text-blue-600">
											{branchUsed.toLocaleString()}
										</span>
									</div>
									<div className="flex flex-col gap-1 flex-1">
										<span className="text-sm text-black-300">Remaining</span>
										<span className="text-sm font-medium text-blue-600">
											{branchRemaining.toLocaleString()}
										</span>
									</div>
								</div>
							</TabsContent>

							<TabsContent value="doctors" className="p-6 m-0 flex flex-col gap-6">
								{/* Token Usage Bar */}
								<div className="bg-blue-50 rounded-lg p-4 flex flex-col gap-3">
									<span className="text-sm text-black-300">Branch Token Usage</span>
									<div className="flex flex-col gap-2">
										<div className="flex justify-between items-center text-sm font-medium">
											<span className="text-black-500">
												<span className="text-blue-600">
													{branchRemaining.toLocaleString()} /{" "}
													{effectiveBranchLimit.toLocaleString()}
												</span>{" "}
												tokens left
											</span>
										</div>
										<div className="h-2 w-full bg-black-50 rounded-full overflow-hidden">
											<div
												className="h-full bg-blue-500 transition-all duration-300"
												style={{
													width: `${effectiveBranchLimit > 0 ? (branchUsed / effectiveBranchLimit) * 100 : 0}%`,
												}}
											/>
										</div>
									</div>
								</div>

								{/* Doctor List */}
								<div className="flex flex-col gap-3">
									<span className="text-sm text-black-300">
										Doctors ({branch.doctors?.length || 0})
									</span>
									<div className="flex flex-col divide-y divide-black-50">
										{branch.doctors?.map((doc) => (
											<div
												key={doc.id}
												className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
											>
												<div className="size-10 rounded-md bg-zinc-100 border border-gray-200 flex items-center justify-center shrink-0 text-zinc-700 font-semibold text-xs select-none">
													{doc.name
														? doc.name
																.split(" ")
																.map((n: string) => n[0])
																.slice(0, 2)
																.join("")
																.toUpperCase()
														: "DR"}
												</div>
												<div className="flex flex-col gap-1 flex-1">
													<div className="flex items-center justify-between">
														<span className="text-sm font-medium text-black-500">{doc.name}</span>
														<span className="text-xs text-zinc-600">
															{doc.dr_type || doc.speciality}
														</span>
													</div>
													<div className="flex items-center justify-between text-xs text-black-300">
														<span>
															Used:{" "}
															<span className="text-zinc-700 font-medium">
																{(doc.tokens_used ?? 0).toLocaleString()}
															</span>{" "}
															tokens
														</span>
														<span>
															<span className="text-blue-600 font-medium">
																{doc.tokensLeft?.toLocaleString() || 0} /{" "}
																{doc.maxTokens?.toLocaleString() || 0}
															</span>{" "}
															tokens left
														</span>
													</div>
												</div>
											</div>
										))}
									</div>
								</div>
							</TabsContent>
						</Tabs>
					</div>
				</SheetContent>
			</Sheet>
		</>
	);
}
