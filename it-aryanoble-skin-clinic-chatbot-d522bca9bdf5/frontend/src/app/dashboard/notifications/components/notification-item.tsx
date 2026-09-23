import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
	RiAlertLine,
	RiArrowRightLine,
	RiBuildingLine,
	RiCheckLine,
	RiFileCopyLine,
	RiThumbDownLine,
	RiThumbUpLine,
} from "@remixicon/react";
import { format } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import { FeedbackNotification } from "../api/types";

interface NotificationItemProps {
	item: FeedbackNotification;
	onMarkAsRead: (id: string) => void;
}

function formatTimestamp(dateString: string) {
	try {
		return format(new Date(dateString), "MMM d, yyyy • h:mm a");
	} catch {
		return dateString;
	}
}

export function NotificationItem({ item, onMarkAsRead }: NotificationItemProps) {
	const isUnread = !item.is_feedback_read;
	const [copied, setCopied] = useState(false);

	const handleCopyId = (e: React.MouseEvent) => {
		e.stopPropagation();
		navigator.clipboard.writeText(item.id);
		setCopied(true);
		setTimeout(() => setCopied(false), 1500);
	};

	return (
		<div
			className={cn(
				"border rounded-lg p-3.5 sm:p-4 flex flex-col gap-3 transition-colors text-xs",
				isUnread
					? "bg-amber-50/40 border-amber-200 hover:border-amber-300"
					: "bg-white border-gray-200 hover:border-gray-300",
			)}
		>
			{/* Top Bar: Doctor, Metadata Badges & Timestamp */}
			<div className="flex items-center justify-between gap-2.5 flex-wrap">
				<div className="flex items-center gap-2 flex-wrap">
					{isUnread && (
						<span
							className="size-1.5 rounded-full bg-amber-500 shrink-0"
							title="Unread notification"
						/>
					)}

					<span className="font-semibold text-gray-900 text-xs sm:text-sm">
						{item.doctor || "Unknown Doctor"}
					</span>

					{item.doctor_type && (
						<Badge
							variant="outline"
							className="text-[10px] font-medium text-gray-600 bg-gray-50 border-gray-200 rounded-md px-1.5 py-0.5"
						>
							{item.doctor_type}
						</Badge>
					)}

					{item.branch && (
						<span className="inline-flex items-center gap-1 text-[11px] text-gray-500 font-medium">
							<RiBuildingLine className="size-3 text-gray-400" />
							{item.branch}
						</span>
					)}

					{/* Rating Badge */}
					{item.rating && (
						<span
							className={cn(
								"inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-md border",
								item.rating === "GOOD"
									? "bg-emerald-50 text-emerald-700 border-emerald-200"
									: "bg-rose-50 text-rose-700 border-rose-200",
							)}
						>
							{item.rating === "GOOD" ? (
								<RiThumbUpLine className="size-3" />
							) : (
								<RiThumbDownLine className="size-3" />
							)}
							{item.rating === "GOOD" ? "Helpful" : "Needs Improvement"}
						</span>
					)}

					{/* Missing Data Flag */}
					{item.has_data_issue && (
						<span className="inline-flex items-center gap-1 text-[10px] font-medium text-rose-700 bg-rose-50 border border-rose-200 px-1.5 py-0.5 rounded-md">
							<RiAlertLine className="size-3 text-rose-600" />
							Missing Knowledge
						</span>
					)}
				</div>

				<span className="text-[11px] text-muted-foreground ml-auto">
					{formatTimestamp(item.updated_at)}
				</span>
			</div>

			{/* Middle Section: Feedback Comment */}
			<div className="space-y-1.5">
				{item.feedback ? (
					<div className="text-gray-800 text-xs leading-relaxed bg-gray-50 border border-gray-200/70 rounded-md p-2.5">
						<span className="font-semibold text-gray-600 text-[11px] block mb-0.5">Doctor Feedback:</span>
						<p className="font-normal text-gray-900">{item.feedback}</p>
					</div>
				) : (
					<p className="text-muted-foreground italic text-[11px]">No written feedback comment provided.</p>
				)}
			</div>

			{/* Bottom Action Footer */}
			<div className="flex items-center justify-between gap-2.5 pt-1 border-t border-gray-100 flex-wrap">
				{/* Compact Session ID with Copy button */}
				<button
					type="button"
					onClick={handleCopyId}
					className="inline-flex items-center gap-1 text-[11px] font-mono text-gray-500 hover:text-gray-800 bg-gray-50 hover:bg-gray-100 border border-gray-200/60 px-2 py-1 rounded-md transition-colors cursor-pointer"
					title="Click to copy full Session ID"
				>
					<RiFileCopyLine className="size-3 text-gray-400" />
					<span>#{item.id.slice(0, 8)}...</span>
					{copied && <span className="text-emerald-600 text-[10px] font-sans font-medium ml-1">Copied!</span>}
				</button>

				{/* Action CTAs */}
				<div className="flex items-center gap-2 ml-auto">
					{isUnread && (
						<Button
							variant="ghost"
							size="sm"
							onClick={() => onMarkAsRead(item.id)}
							className="h-8 px-2.5 text-xs text-amber-800 hover:text-amber-950 hover:bg-amber-100/70 font-medium rounded-lg shadow-none cursor-pointer"
						>
							<RiCheckLine className="size-3.5 mr-1" />
							Mark as read
						</Button>
					)}

					{/* Prominent Chat Redirect CTA */}
					<Link href={`/dashboard/chat-history/${item.id}`}>
						<Button
							variant="default"
							size="sm"
							className="h-8 px-3 text-xs bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-none gap-1.5 transition-colors cursor-pointer"
						>
							<span>View Chat Session</span>
							<RiArrowRightLine className="size-3.5" />
						</Button>
					</Link>
				</div>
			</div>
		</div>
	);
}
