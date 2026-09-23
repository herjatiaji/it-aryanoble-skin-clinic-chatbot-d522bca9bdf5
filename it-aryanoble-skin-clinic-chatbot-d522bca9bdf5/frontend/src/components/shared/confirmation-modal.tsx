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
import { RiLoader4Line } from "@remixicon/react";

interface ConfirmationModalProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	title: string;
	description: string;
	confirmText?: string;
	cancelText?: string;
	variant?: "primary" | "destructive";
	isLoading?: boolean;
	onConfirm: () => void | Promise<void>;
	onCancel?: () => void;
}

export function ConfirmationModal({
	isOpen,
	onOpenChange,
	title,
	description,
	confirmText = "Confirm",
	cancelText = "Cancel",
	variant = "primary",
	isLoading = false,
	onConfirm,
	onCancel,
}: ConfirmationModalProps) {
	const handleCancel = () => {
		onOpenChange(false);
		onCancel?.();
	};

	const handleConfirm = async () => {
		await onConfirm();
		onOpenChange(false);
	};

	const handleOpenChange = (open: boolean) => {
		if (!open && isLoading) return;
		onOpenChange(open);
	};

	return (
		<Dialog open={isOpen} onOpenChange={handleOpenChange}>
			<DialogContent className="sm:max-w-100 w-full p-0 flex flex-col gap-0 rounded-lg overflow-hidden bg-white border border-gray-200 shadow-none">
				{/* Title Section */}
				<DialogHeader className="p-4 pb-2 border-none">
					<DialogTitle className="text-base font-semibold text-foreground text-left">
						{title}
					</DialogTitle>
				</DialogHeader>

				{/* Body Content Section */}
				<div className="px-4 py-2">
					<DialogDescription className="text-sm text-muted-foreground font-normal leading-relaxed text-left">
						{description}
					</DialogDescription>
				</div>

				{/* Footer Actions */}
				<DialogFooter className="p-4 pt-4 flex flex-row items-center justify-end gap-2.5 sm:justify-end border-none">
					<Button
						type="button"
						variant="outline"
						onClick={handleCancel}
						disabled={isLoading}
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
					>
						{cancelText}
					</Button>
					<Button
						type="button"
						onClick={handleConfirm}
						disabled={isLoading}
						className={`rounded-lg px-4 h-10 font-medium text-sm text-white shadow-none transition-colors cursor-pointer ${
							variant === "destructive"
								? "bg-red-600 hover:bg-red-700"
								: "bg-blue-600 hover:bg-blue-700"
						}`}
					>
						{isLoading && <RiLoader4Line className="size-4 animate-spin mr-1.5" />}
						{confirmText}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
