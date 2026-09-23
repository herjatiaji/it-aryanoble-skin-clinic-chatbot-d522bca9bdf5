"use client";

import { SearchBar } from "@/components/shared/search-bar";
import { ChatFilter } from "./components/chat-filter";
import { ChatHistoryList } from "./components/chat-history-list";
import { ChatHistorySummary } from "./components/chat-history-summary";
import { useChatHistoryState } from "./hooks/use-chat-history-state";

export default function ChatHistoryPage() {
	const {
		isLoading,
		isError,
		filteredData,
		users,
		chatTypes,
		hasActiveFilters,
		userFilter,
		setUserFilter,
		chatTypeFilter,
		setChatTypeFilter,
		dateRange,
		setDateRange,
		searchQuery,
		setSearchQuery,
		handleResetFilters,
		pagination,
	} = useChatHistoryState();

	return (
		<div className="flex flex-col min-h-full gap-6 p-6 pb-12">
			{/* Overview Summary Cards */}
			<ChatHistorySummary items={filteredData} />

			<div className="flex flex-col gap-4">
				{/* Toolbar */}
				<div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
					<SearchBar
						containerClassName="max-w-md w-full"
						placeholder="Search for chat sessions..."
						value={searchQuery}
						onChange={(e) => setSearchQuery(e.target.value)}
					/>
					<ChatFilter
						users={users}
						userFilter={userFilter}
						onUserChange={setUserFilter}
						chatTypes={chatTypes}
						chatTypeFilter={chatTypeFilter}
						onChatTypeChange={setChatTypeFilter}
						dateRange={dateRange}
						onDateRangeChange={setDateRange}
					/>
				</div>

				{/* List */}
				<ChatHistoryList
					isLoading={isLoading}
					isError={isError}
					filteredData={filteredData}
					paginatedItems={pagination.paginatedItems}
					hasActiveFilters={hasActiveFilters}
					onResetFilters={handleResetFilters}
					pagination={pagination}
				/>
			</div>
		</div>
	);
}
