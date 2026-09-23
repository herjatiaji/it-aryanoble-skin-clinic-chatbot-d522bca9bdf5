import { useMemo } from "react";
import Image from "next/image";
import { useChatStats } from "../hooks/use-chat-history";
import type { ChatHistoryResponse } from "../api/types";

interface ChatHistorySummaryProps {
	doctorId?: string;
	items?: ChatHistoryResponse[];
}

export function ChatHistorySummary({ doctorId, items }: ChatHistorySummaryProps) {
	const { data: serverStats } = useChatStats(doctorId);

	const stats = useMemo(() => {
		if (items !== undefined) {
			const doctorItems = items.filter(
				(item) =>
					item.user_type === "DOCTOR" ||
					(item.user_type !== "STAFF" &&
						item.user_type !== "ADMIN" &&
						item.session_type !== "GENERAL_ASSISTANT")
			);

			const uniqueDoctors = new Set(
				doctorItems
					.map((item) => item.user_name || item.doctor || item.user_id)
					.filter((doc): doc is string => Boolean(doc && doc !== "Unknown"))
			);

			return {
				doctors_reached: uniqueDoctors.size,
				total_sessions: doctorItems.length,
				positive_ratings: doctorItems.filter(
					(item) => item.rating === "GOOD" || item.rating === "4" || item.rating === "5"
				).length,
				negative_ratings: doctorItems.filter(
					(item) => item.rating === "BAD" || item.rating === "1" || item.rating === "2"
				).length,
				missing_knowledge: doctorItems.filter((item) => Boolean(item.has_data_issue)).length,
			};
		}
		return serverStats;
	}, [items, serverStats]);

	const summaries = [
		{
			title: "Users Reached",
			count: stats?.doctors_reached ?? 0,
			iconSrc: "/icons/users.png",
			iconBg: "bg-[#e7fcf2]",
		},
		{
			title: "Total Sessions",
			count: stats?.total_sessions ?? 0,
			iconSrc: "/icons/messages-square.png",
			iconBg: "bg-[#e6f2fe]",
		},
		{
			title: "Positive Ratings",
			count: stats?.positive_ratings ?? 0,
			iconSrc: "/icons/thumbs-up.png",
			iconBg: "bg-[#e7fcf2]",
		},
		{
			title: "Negative Ratings",
			count: stats?.negative_ratings ?? 0,
			iconSrc: "/icons/thumbs-down.png",
			iconBg: "bg-[#fce7e7]",
		},
		{
			title: "Missing Knowledge",
			count: stats?.missing_knowledge ?? 0,
			iconSrc: "/icons/search-x.png",
			iconBg: "bg-[#fffae8]",
		},
	];

	return (
		<div className="w-full">
			<div className="mb-4">
				<h2 className="text-xl font-semibold text-gray-900">Chat History</h2>
				<p className="text-sm text-zinc-600 mt-1">View past chats with the AI chatbot easily.</p>
			</div>
			<div className="w-full overflow-x-auto pb-1">
				<div className="w-full min-w-190 flex items-center border border-gray-200 rounded-md bg-white overflow-hidden shadow-none">
					{summaries.map((item, index) => (
						<div
							key={item.title}
							className={`flex-1 min-w-0 flex items-center gap-4 p-4 ${
								index !== summaries.length - 1 ? "border-r border-gray-200" : ""
							}`}
						>
							<div className={`w-12 h-12 rounded-lg flex items-center justify-center shrink-0 ${item.iconBg}`}>
								<Image
									src={item.iconSrc}
									alt={item.title}
									width={24}
									height={24}
									className="shrink-0 size-6 object-contain"
								/>
							</div>
							<div className="min-w-0">
								<p className="text-sm text-zinc-600 truncate">{item.title}</p>
								<p className="text-2xl font-medium text-gray-900 mt-1">{item.count}</p>
							</div>
						</div>
					))}
				</div>
			</div>
		</div>
	);
}

