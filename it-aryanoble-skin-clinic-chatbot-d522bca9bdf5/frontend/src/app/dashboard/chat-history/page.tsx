"use client";
import { useState } from "react";
import { SearchBar } from "@/components/shared/search-bar";
import { RiLoader4Line } from "@remixicon/react";
import { ChatFilter } from "./components/chat-filter";
import { ChatHistoryCard } from "./components/chat-history-card";
import { useChatHistories } from "./hooks/use-chat-history";
import { useUsers } from "@/app/dashboard/users/hooks/use-users";

export default function ChatHistoryPage() {
	const { data: chatHistories, isLoading, isError } = useChatHistories();
	const { data: allDoctors } = useUsers("DOCTOR");
	const [doctorFilter, setDoctorFilter] = useState("ALL");

	// Get names of all registered doctors
	const doctors = allDoctors?.map((user) => user.name) || [];

	const filteredData = chatHistories?.filter((item) => {
		if (doctorFilter !== "ALL" && item.doctor !== doctorFilter) return false;
		return true;
	});

	return (
		<div className="flex flex-col h-full gap-6 p-6">
			{/* Header */}
			<div className="flex flex-col gap-1">
				<h1 className="text-xl font-semibold text-foreground">Chat History</h1>
				<p className="text-sm text-muted-foreground">View past chats with the AI chatbot easily.</p>
			</div>

			<div className="flex flex-col gap-4">
				{/* Toolbar */}
				<div className="flex items-center justify-between">
					<SearchBar
						containerClassName="max-w-md"
						placeholder="Search for chat sessions..."
					/>
					<ChatFilter 
						doctors={doctors} 
						value={doctorFilter} 
						onChange={setDoctorFilter} 
					/>
				</div>

			{/* List */}
			<div className="flex flex-col gap-4">
				{isLoading && (
					<div className="flex items-center justify-center p-8 text-muted-foreground">
						<RiLoader4Line className="w-6 h-6 animate-spin" />
						<span className="ml-2">Loading chat histories...</span>
					</div>
				)}

				{isError && (
					<div className="p-4 text-sm text-red-500 bg-red-50 rounded-md">
						Failed to load chat history.
					</div>
				)}

				{!isLoading && !isError && filteredData?.length === 0 && (
					<div className="p-8 text-center text-muted-foreground">No chat history found.</div>
				)}

				{!isLoading &&
					!isError &&
					filteredData?.map((item) => <ChatHistoryCard key={item.id} item={item} />)}
			</div>
			</div>
		</div>
	);
}
