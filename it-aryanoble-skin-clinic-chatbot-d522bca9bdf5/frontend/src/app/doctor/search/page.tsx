"use client";

import {
	RiRobot2Line,
	RiSearchLine,
	RiCalendarLine,
	RiMessageAi3Line,
	RiLoader4Line,
} from "@remixicon/react";
import { Input } from "@/components/ui/input";
import { useChatSessions } from "../hooks/use-doctor-chat";
import { useRouter } from "next/navigation";

export default function DoctorSearchPage() {
	const router = useRouter();
	const { data: chatSessions, isLoading, isError } = useChatSessions();

	return (
		<div className="flex flex-col max-w-2xl mx-auto min-h-full w-full px-4">
			{/* Sticky Top Section */}
			<div className="sticky top-0 z-10 bg-white pt-10 pb-8">
				{/* Header */}
				<div className="flex flex-col items-center text-center space-y-2 mb-8">
					<div className="flex aspect-square size-8 items-center justify-center rounded-md bg-blue-50 text-blue-500">
						<RiRobot2Line className="size-4" />
					</div>
					<h1 className="text-lg font-semibold tracking-tight text-zinc-950">
						Hello Doctor, I&apos;m Ready to Help!
					</h1>
				</div>

				{/* Search Bar */}
				<div className="relative">
					<div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
						<RiSearchLine className="size-5 text-zinc-950" />
					</div>
					<Input
						type="text"
						className="w-full bg-white-500 rounded-md py-3 pl-11 pr-4 text-sm text-zinc-950 placeholder:text-zinc-500 border-transparent focus-visible:border-blue-500 shadow-sm"
						placeholder="Enter a keyword to search the chat"
					/>
				</div>
			</div>

			{/* Search Results */}
			<div className="space-y-3 pb-12">
				{isLoading && (
					<div className="flex items-center justify-center py-8 text-zinc-500">
						<RiLoader4Line className="size-6 animate-spin" />
						<span className="ml-2 text-sm">Loading chats...</span>
					</div>
				)}

				{isError && (
					<div className="text-center py-8 text-sm text-red-500">Failed to load chat history.</div>
				)}

				{!isLoading && !isError && chatSessions?.length === 0 && (
					<div className="text-center py-8 text-sm text-zinc-500">
						No active chat sessions found. Start a new one!
					</div>
				)}

				{!isLoading &&
					chatSessions?.map((chat) => {
						const formattedDate = new Intl.DateTimeFormat("en-US", {
							month: "short",
							day: "numeric",
							year: "numeric",
							hour: "numeric",
							minute: "2-digit",
						}).format(new Date(chat.created_at));

						return (
							<div
								key={chat.id}
								onClick={() => router.push(`/doctor/chat/${chat.id}`)}
								className="bg-white rounded-md p-3 border border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50 transition-colors cursor-pointer block"
							>
								<p className="text-zinc-950 text-sm font-medium leading-snug truncate mb-2">
									{chat.query || "New Chat Session"}
								</p>
								<div className="flex items-center gap-4 mt-auto">
									<div className="flex items-center text-zinc-500">
										<RiCalendarLine className="size-4 mr-1 text-zinc-950" />
										<span className="text-xs">{formattedDate}</span>
									</div>
									<div className="flex items-center text-zinc-500 ml-auto">
										<RiMessageAi3Line className="size-4 mr-1 text-zinc-950" />
										<span className="text-xs">{chat.messages} Messages</span>
									</div>
								</div>
							</div>
						);
					})}
				{/* Explicit physical spacer for bottom gap */}
				<div className="h-12 w-full shrink-0" />
			</div>
		</div>
	);
}
