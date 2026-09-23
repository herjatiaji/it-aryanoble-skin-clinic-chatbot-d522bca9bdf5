"use client";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldContent, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RiAddLine, RiCheckLine, RiDeleteBinLine, RiLoader4Line } from "@remixicon/react";
import { RoleDetailResponse } from "../api/types";
import { useRoleForm } from "../hooks/use-role-form";
import { DeleteRoleDialog } from "./delete-role-dialog";
import { RolePermissionMatrix } from "./role-permission-matrix";

interface RoleDialogProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	role: RoleDetailResponse | null;
	mode: "add" | "edit";
}

export function RoleDialog({ isOpen, onOpenChange, role, mode }: RoleDialogProps) {
	const {
		name,
		setName,
		selectedUiKeys,
		isDeleteDialogOpen,
		setIsDeleteDialogOpen,
		toggleGlobalSelectAll,
		toggleModule,
		toggleAction,
		handleSave,
		handleDeleteClick,
		handleConfirmDelete,
		isPending,
		isSystemAdmin,
	} = useRoleForm({ isOpen, onOpenChange, role, mode });

	return (
		<>
			<Dialog open={isOpen} onOpenChange={onOpenChange}>
				<DialogContent
					showCloseButton={true}
					className="sm:max-w-3xl max-h-[90vh] p-0 flex flex-col bg-white rounded-lg overflow-hidden shadow-none border border-gray-200"
				>
					{/* Modal Header */}
					<DialogHeader className="p-4 sm:p-5 border-b border-gray-100 flex flex-row items-center justify-between shrink-0">
						<DialogTitle className="text-base font-semibold text-foreground">
							{mode === "add" ? "Add New Role" : `Edit Role: ${role?.name}`}
						</DialogTitle>
					</DialogHeader>

					{/* Modal Content Body */}
					<div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
						{/* Role Name */}
						<Field>
							<FieldLabel>
								<FieldTitle className="text-sm font-normal text-gray-900">Role Name</FieldTitle>
							</FieldLabel>
							<FieldContent>
								<div className="relative">
									<Input
										placeholder="Head Department Functional"
										value={name}
										onChange={(e) => setName(e.target.value)}
										disabled={isSystemAdmin}
										className="border-gray-200 bg-white focus-visible:ring-blue-500 font-normal text-sm h-10 rounded-lg uppercase"
									/>
								</div>
								{isSystemAdmin && (
									<p className="text-xs text-amber-600 mt-1">
										The default ADMIN role name is protected and cannot be modified.
									</p>
								)}
							</FieldContent>
						</Field>

						{/* Role Permission Section */}
						<RolePermissionMatrix
							selectedUiKeys={selectedUiKeys}
							onToggleGlobalSelectAll={toggleGlobalSelectAll}
							onToggleModule={toggleModule}
							onToggleAction={toggleAction}
						/>
					</div>

					{/* Modal Footer */}
					<div className="p-4 border-t border-gray-100 bg-white flex items-center justify-between shrink-0">
						{mode === "edit" && !isSystemAdmin ? (
							<Button
								variant="outline"
								className="border-red-200 text-red-600 hover:bg-red-50 hover:border-red-300 px-4 h-10 rounded-lg font-medium text-sm transition-colors cursor-pointer shadow-none"
								onClick={handleDeleteClick}
								disabled={isPending}
							>
								<RiDeleteBinLine className="mr-2 h-4 w-4 shrink-0" />
								Delete Role
							</Button>
						) : (
							<div />
						)}

						<div className="flex items-center gap-3">
							<Button
								variant="outline"
								className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
								onClick={() => onOpenChange(false)}
							>
								Cancel
							</Button>
							<Button
								className="bg-blue-600 text-white hover:bg-blue-700 px-4 h-10 rounded-lg font-medium text-sm transition-colors cursor-pointer shadow-none"
								onClick={handleSave}
								disabled={isPending || !name.trim()}
							>
								{isPending ? (
									<RiLoader4Line className="mr-2 h-4 w-4 animate-spin shrink-0" />
								) : mode === "add" ? (
									<RiAddLine className="mr-2 h-4 w-4 shrink-0" />
								) : (
									<RiCheckLine className="mr-2 h-4 w-4 shrink-0" />
								)}
								{isPending ? "Saving..." : mode === "add" ? "Add Role" : "Save Changes"}
							</Button>
						</div>
					</div>
				</DialogContent>
			</Dialog>

			<DeleteRoleDialog
				isOpen={isDeleteDialogOpen}
				onOpenChange={setIsDeleteDialogOpen}
				roleName={role?.name}
				isPending={isPending}
				onConfirm={handleConfirmDelete}
			/>
		</>
	);
}
