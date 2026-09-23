"use client";

import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogMedia,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { RiTimerLine } from "@remixicon/react";

interface IdleTimeoutDialogProps {
	open: boolean;
	remainingSeconds: number;
	onStayLoggedIn: () => void;
	onLogoutNow: () => void;
}

export function IdleTimeoutDialog({
	open,
	remainingSeconds,
	onStayLoggedIn,
	onLogoutNow,
}: IdleTimeoutDialogProps) {
	return (
		<AlertDialog open={open}>
			<AlertDialogContent className="sm:max-w-md p-0 flex flex-col gap-0 rounded-lg overflow-hidden bg-white border border-gray-200 shadow-none ring-0">
				<AlertDialogHeader className="p-5 pb-4 border-b border-gray-100 flex flex-row items-start gap-3.5 text-left">
					<AlertDialogMedia className="size-10 rounded-lg bg-amber-50 text-amber-600 border border-amber-200/60 flex items-center justify-center shrink-0 mb-0">
						<RiTimerLine className="size-5" />
					</AlertDialogMedia>
					<div className="flex flex-col gap-1">
						<AlertDialogTitle className="text-base font-semibold text-gray-900 leading-tight">
							Session Inactivity Warning
						</AlertDialogTitle>
						<AlertDialogDescription className="text-xs sm:text-sm text-zinc-600 leading-relaxed">
							You have been inactive for a while. To protect clinic data, your session will
							automatically close in{" "}
							<span className="font-semibold text-gray-900">{remainingSeconds}s</span>.
						</AlertDialogDescription>
					</div>
				</AlertDialogHeader>

				<AlertDialogFooter className="p-4 border-t border-gray-100 bg-gray-50/60 flex flex-row items-center justify-end gap-2.5">
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={onLogoutNow}
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg shadow-none font-medium h-9 text-xs sm:text-sm"
					>
						Logout Now
					</Button>
					<AlertDialogAction
						type="button"
						size="sm"
						onClick={onStayLoggedIn}
						className="bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-none h-9 text-xs sm:text-sm px-4 cursor-pointer"
					>
						Stay Logged In
					</AlertDialogAction>
				</AlertDialogFooter>
			</AlertDialogContent>
		</AlertDialog>
	);
}
