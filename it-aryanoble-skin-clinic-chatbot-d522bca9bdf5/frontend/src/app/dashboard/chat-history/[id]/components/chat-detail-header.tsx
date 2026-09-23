import { Button } from "@/components/ui/button";
import { RiArrowLeftLine, RiMessage3Line, RiThumbDownLine, RiThumbUpLine } from "@remixicon/react";
import type { ChatHistoryResponse } from "../../api/types";

interface ChatDetailHeaderProps {
	sessionTitle: string;
	session?: ChatHistoryResponse;
	isOwner: boolean;
	isStaffOrAdmin: boolean;
	isGeneralChat: boolean;
	sessionId: string;
	onBack: () => void;
	onContinueChat: () => void;
}

export function ChatDetailHeader({
	sessionTitle,
	session,
	isOwner,
	isStaffOrAdmin,
	isGeneralChat,
	onBack,
	onContinueChat,
}: ChatDetailHeaderProps) {
	return (
		<div className="flex items-center justify-between gap-4 px-4 py-3 border-b border-gray-200 shrink-0 bg-white z-10">
			<div className="flex items-center gap-3 min-w-0">
				<Button
					variant="ghost"
					size="icon"
					onClick={onBack}
					className="size-9 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 shrink-0"
					title="Back"
					aria-label="Back"
				>
					<RiArrowLeftLine className="size-5" />
				</Button>
				<div className="min-w-0">
					<h1 className="text-base font-semibold text-gray-900 truncate">{sessionTitle}</h1>
				</div>
			</div>

			<div className="flex items-center gap-2 shrink-0">
				{isOwner && isStaffOrAdmin && isGeneralChat && (
					<Button
						variant="outline"
						size="sm"
						onClick={onContinueChat}
						className="gap-1.5 border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 text-xs font-medium h-7 px-2.5 rounded-md cursor-pointer"
					>
						<RiMessage3Line className="size-3.5" />
						Continue Chat
					</Button>
				)}
				{session?.rating && (
					<span
						className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${
							session.rating === "GOOD"
								? "bg-emerald-50 text-emerald-700 border-emerald-200"
								: "bg-red-50 text-red-700 border-red-200"
						}`}
					>
						{session.rating === "GOOD" ? (
							<RiThumbUpLine className="size-3.5" />
						) : (
							<RiThumbDownLine className="size-3.5" />
						)}
						<span>{session.rating === "GOOD" ? "Helpful" : "Needs Improvement"}</span>
					</span>
				)}
				<span className="bg-zinc-50 text-zinc-600 border border-zinc-200 px-2.5 py-1 rounded-md text-xs font-medium">
					Read-only Archive
				</span>
			</div>
		</div>
	);
}
