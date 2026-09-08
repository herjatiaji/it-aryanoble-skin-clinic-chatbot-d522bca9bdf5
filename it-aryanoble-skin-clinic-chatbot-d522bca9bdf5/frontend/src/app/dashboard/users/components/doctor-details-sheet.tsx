"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { RiEdit2Line, RiSettings3Line } from "@remixicon/react";
import Image from "next/image";
import { useState } from "react";
import { UserResponse } from "../api/types";
import { DoctorAdjustLimitDialog } from "./doctor-adjust-limit-dialog";
import { DoctorManageKnowledgeDialog } from "./doctor-manage-knowledge-dialog";

export function DoctorDetailsSheet({
	isOpen,
	onOpenChange,
	doctor,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	doctor: UserResponse | null;
}) {
	const [isManageKnowledgeOpen, setIsManageKnowledgeOpen] = useState(false);
	const [isAdjustLimitOpen, setIsAdjustLimitOpen] = useState(false);
	return (
		<Sheet open={isOpen} onOpenChange={onOpenChange}>
			<SheetContent className="sm:max-w-100 p-0 flex flex-col h-full bg-white gap-0">
				<SheetHeader className="p-4 border-b flex flex-row items-center">
					<SheetTitle className="text-base font-medium">Doctor Information</SheetTitle>
				</SheetHeader>

				{doctor && (
					<>
						<div className="flex-1 overflow-y-auto pb-6">
							<div className="flex flex-col pb-4">
								{/* Profile Cover Image */}
								<div className="relative h-65 w-full bg-gray-100 overflow-hidden shrink-0">
									<Image src="/placeholder.svg" alt={doctor.name} fill className="object-cover" />
									<div className="absolute top-4 right-4 z-10"></div>
								</div>

								{/* Details Section */}
								<div className="flex flex-col gap-4 px-6 py-4">
									<div className="flex flex-col gap-2">
										<span className="text-sm text-gray-500">Name</span>
										<span className="text-sm text-gray-900">{doctor.name}</span>
									</div>

									<div className="flex flex-col gap-2">
										<span className="text-sm text-gray-500">Role</span>
										<span className="text-sm text-gray-900">Doctor</span>
									</div>

									<div className="flex flex-col gap-2">
										<span className="text-sm text-gray-500">Email</span>
										<span className="text-sm text-gray-900">{doctor.email}</span>
									</div>

									<div className="flex flex-col gap-2">
										<span className="text-sm text-gray-500">Employee ID</span>
										<span className="text-sm text-gray-900">{doctor.employee_id || "-"}</span>
									</div>

									<div className="flex flex-col gap-2">
										<span className="text-sm text-gray-500">Dr Type</span>
										<span className="text-sm text-gray-900">{doctor.dr_type || "-"}</span>
									</div>

									<div className="flex flex-col gap-2">
										<span className="text-sm text-gray-500">Ecosystem</span>
										<span className="text-sm text-gray-900">{doctor.ecosystem || "ERHA"}</span>
									</div>

									<div className="flex flex-col gap-2">
										<div className="flex justify-between items-center">
											<div className="flex flex-col gap-2">
												<span className="text-sm text-gray-500">Tokens Remaining</span>
												<span className="text-sm text-gray-900">
													{doctor.token_limit !== undefined && doctor.tokens_used !== undefined
														? doctor.token_limit - doctor.tokens_used
														: 0}{" "}
													/ {doctor.token_limit ?? 0} tokens
												</span>
											</div>
											<Button
												variant="outline"
												className=""
												onClick={() => setIsAdjustLimitOpen(true)}
											>
												<RiEdit2Line className="mr-2 h-4 w-4" />
												Adjust Limit
											</Button>
										</div>
									</div>

									<div className="flex flex-col gap-2 pt-2">
										<span className="text-sm text-gray-500">Branches</span>
										{doctor.branches && doctor.branches.length > 0 ? (
											<div className="flex flex-col gap-3">
												{doctor.branches.map((branch) => (
													<div
														key={branch.id}
														className="border border-gray-200 rounded-md p-3 flex flex-col gap-3"
													>
														<div className="flex flex-col">
															<span className="text-sm font-medium text-gray-900">
																{branch.name}
															</span>
														</div>
													</div>
												))}
											</div>
										) : (
											<div className="border border-gray-200 rounded-md p-3">
												<span className="text-sm text-gray-500">No Branch</span>
											</div>
										)}
									</div>

									<div className="flex flex-col gap-2 pt-2">
										<span className="text-sm text-gray-500">Knowledge Base</span>
										<div className="flex flex-wrap gap-2">
											{doctor.categories && doctor.categories.length > 0 ? (
												doctor.categories.map((cat) => (
													<Badge
														key={cat.id}
														variant="secondary"
														className="bg-gray-100 text-gray-900"
													>
														{cat.name}
													</Badge>
												))
											) : (
												<span className="text-sm text-gray-400">No categories assigned</span>
											)}
										</div>
										<Button
											variant="outline"
											className="w-full mt-2 rounded-md"
											onClick={() => setIsManageKnowledgeOpen(true)}
										>
											<RiSettings3Line className="mr-2 h-4 w-4" />
											Manage Knowledge Base
										</Button>
									</div>
								</div>
							</div>
						</div>

						<div className="p-4 border-t border-gray-200 bg-white flex justify-start gap-3">
							<Button
								variant="outline"
								className="bg-white border-gray-200 text-gray-700 hover:bg-gray-50 hover:text-gray-900"
								onClick={() => onOpenChange(false)}
							>
								Close
							</Button>
						</div>

						<DoctorManageKnowledgeDialog
							isOpen={isManageKnowledgeOpen}
							onOpenChange={setIsManageKnowledgeOpen}
							doctor={doctor}
						/>

						<DoctorAdjustLimitDialog
							isOpen={isAdjustLimitOpen}
							onOpenChange={setIsAdjustLimitOpen}
							doctor={doctor}
						/>
					</>
				)}
			</SheetContent>
		</Sheet>
	);
}
