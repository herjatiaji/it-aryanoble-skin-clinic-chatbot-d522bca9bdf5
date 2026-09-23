import { Button } from "@/components/ui/button";
import { useSafeBack } from "@/hooks/use-safe-back";
import { RiArrowLeftLine, RiRefreshLine } from "@remixicon/react";

interface ChatHeaderProps {
	isCreatingSession?: boolean;
	onNewSession: () => void;
}

export function ChatHeader({ isCreatingSession, onNewSession }: ChatHeaderProps) {
	const handleBack = useSafeBack("/dashboard/ingest");

	return (
		<div className="flex items-center justify-between gap-4 px-4 py-3 border-b border-gray-200 shrink-0 bg-white">
			<div className="flex items-center gap-3">
				<Button
					variant="ghost"
					size="icon"
					onClick={handleBack}
					className="size-9 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100"
					title="Back"
					aria-label="Back"
				>
					<RiArrowLeftLine className="size-5" />
				</Button>
				<h1 className="text-base font-semibold text-gray-900">General Knowledge Assistant</h1>
			</div>

			<div className="flex items-center gap-2">
				<Button
					variant="outline"
					onClick={onNewSession}
					disabled={isCreatingSession}
					className="gap-2 border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
				>
					<RiRefreshLine className="size-4" />
					New Session
				</Button>
			</div>
		</div>
	);
}
