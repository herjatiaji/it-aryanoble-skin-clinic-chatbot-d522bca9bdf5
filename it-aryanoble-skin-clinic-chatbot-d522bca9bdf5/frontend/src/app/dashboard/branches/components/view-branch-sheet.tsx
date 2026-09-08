"use client";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Image from "next/image";
import { RiEyeLine } from "@remixicon/react";
import * as React from "react";
import { BranchResponse } from "../../configuration/api/types";
import { EditBranchTokenDialog } from "./edit-branch-token-dialog";

interface ViewBranchSheetProps {
	branch: BranchResponse;
}

export function ViewBranchSheet({ branch }: ViewBranchSheetProps) {
	const [open, setOpen] = React.useState(false);

	return (
		<>
			<Button
				variant="outline"
				className="bg-white border-black-50 text-black-500 rounded-lg font-medium hover:bg-zinc-50 shadow-none"
				onClick={() => setOpen(true)}
			>
				<RiEyeLine className="size-4 mr-2" />
				View
			</Button>
			<Sheet open={open} onOpenChange={setOpen}>
				<SheetContent className="sm:max-w-100 w-full p-0 flex flex-col gap-0 border-l border-black-50 bg-white">
					<SheetHeader className="p-4 border-b border-black-50">
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
										className="font-medium text-sm text-gray-500 hover:text-blue-500 data-active:text-blue-500 data-active:after:bg-blue-500 px-0 pb-2"
									>
										Branch Information
									</TabsTrigger>
									<TabsTrigger
										value="doctors"
										className="font-medium text-sm text-gray-500 hover:text-blue-500 data-active:text-blue-500 data-active:after:bg-blue-500 px-0 pb-2"
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

								<div className="flex items-center justify-between gap-4">
									<div className="flex flex-col gap-1">
										<span className="text-sm text-black-300">Tokens</span>
										<span className="text-sm font-medium text-blue-600">
											{branch.tokensMonth} <span className="text-black-500 font-normal">/month</span>
										</span>
									</div>
									<EditBranchTokenDialog branch={branch} />
								</div>

								<div className="flex items-center gap-4">
									<div className="flex flex-col gap-1 flex-1">
										<span className="text-sm text-black-300">Used</span>
										<span className="text-sm font-medium text-blue-600">{branch.used}</span>
									</div>
									<div className="flex flex-col gap-1 flex-1">
										<span className="text-sm text-black-300">Remaining</span>
										<span className="text-sm font-medium text-blue-600">{branch.remaining}</span>
									</div>
								</div>
							</TabsContent>

							<TabsContent value="doctors" className="p-6 m-0 flex flex-col gap-6">
								{/* Token Usage Bar */}
								<div className="bg-blue-50 rounded-lg p-4 flex flex-col gap-3">
									<span className="text-sm text-black-300">Token Usage</span>
									<div className="flex flex-col gap-2">
										<div className="flex justify-between items-center text-sm font-medium">
											<span className="text-black-500">
												<span className="text-blue-600">{branch.remaining}/{branch.tokensMonth}</span> tokens left
											</span>
										</div>
										<div className="h-2 w-full bg-black-50 rounded-full overflow-hidden">
											<div
												className="h-full bg-blue-500"
												style={{ width: `${(branch.used / branch.tokensMonth) * 100}%` }}
											/>
										</div>
									</div>
								</div>

								{/* Doctor List */}
								<div className="flex flex-col gap-3">
									<span className="text-sm text-black-300">
										Doctor ({branch.doctors?.length || 0})
									</span>
									<div className="flex flex-col divide-y divide-black-50">
										{branch.doctors?.map((doc) => (
											<div key={doc.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
												<div className="size-10 rounded-md bg-zinc-200 shrink-0 overflow-hidden">
													<Image
														src="/mini-placeholder.svg"
														alt={doc.name}
														width={40}
														height={40}
														className="object-cover h-full w-full"
													/>
												</div>
												<div className="flex flex-col gap-1 flex-1">
													<span className="text-sm font-medium text-black-500">{doc.name}</span>
													<span className="text-xs text-black-300">
														<span className="text-blue-600 font-medium">{doc.tokensLeft}/{doc.maxTokens}</span> tokens left
													</span>
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
