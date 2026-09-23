"use client";

import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { RiDeleteBinLine, RiLoader4Line } from "@remixicon/react";

interface DeleteRoleDialogProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	roleName?: string;
	isPending: boolean;
	onConfirm: () => void;
}

export function DeleteRoleDialog({
	isOpen,
	onOpenChange,
	roleName,
	isPending,
	onConfirm,
}: DeleteRoleDialogProps) {
	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-md p-0 flex flex-col gap-0 rounded-lg overflow-hidden bg-white border border-gray-200 shadow-none">
				<DialogHeader className="p-5 pb-2">
					<DialogTitle className="text-base font-semibold text-foreground text-left">
						Delete Role
					</DialogTitle>
				</DialogHeader>

				<div className="px-5 py-2">
					<DialogDescription className="text-sm text-muted-foreground leading-relaxed text-left">
						Are you sure you want to delete the role{" "}
						<span className="font-semibold text-foreground">&quot;{roleName}&quot;</span>? This
						action cannot be undone and will remove associated permissions for users assigned to
						this role.
					</DialogDescription>
				</div>

				<DialogFooter className="p-5 pt-4 flex flex-row items-center justify-end gap-3 border-t border-gray-100 bg-gray-50/50">
					<Button
						type="button"
						variant="outline"
						onClick={() => onOpenChange(false)}
						disabled={isPending}
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
					>
						Cancel
					</Button>
					<Button
						type="button"
						onClick={onConfirm}
						disabled={isPending}
						className="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 h-10 font-medium text-sm shadow-none transition-colors cursor-pointer"
					>
						{isPending ? (
							<RiLoader4Line className="mr-1.5 h-4 w-4 animate-spin" />
						) : (
							<RiDeleteBinLine className="mr-1.5 h-4 w-4" />
						)}
						{isPending ? "Deleting..." : "Delete Role"}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
