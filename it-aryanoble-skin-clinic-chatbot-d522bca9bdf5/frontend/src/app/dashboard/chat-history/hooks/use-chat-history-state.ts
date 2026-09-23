import { useUsers } from "@/app/dashboard/users/hooks/use-users";
import { useDebounce } from "@/hooks/use-debounce";
import { usePagination } from "@/hooks/use-pagination";
import { useMemo, useState } from "react";
import type { DateRange } from "react-day-picker";
import type { ChatHistoryResponse } from "../api/types";
import { useChatHistories } from "./use-chat-history";

export interface ChatTypeOption {
	value: string;
	label: string;
}

export function useChatHistoryState() {
	const { data: chatHistories, isLoading, isError } = useChatHistories();
	const { data: allUsers } = useUsers();

	const [userFilter, setUserFilter] = useState("ALL");
	const [chatTypeFilter, setChatTypeFilter] = useState("ALL");
	const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);
	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 300);

	// Combine all registered users and users from chat histories
	const users = useMemo(() => {
		const userSet = new Set<string>();
		allUsers?.forEach((u) => {
			if (u.name) userSet.add(u.name);
		});
		chatHistories?.forEach((h) => {
			const name = h.user_name || h.doctor;
			if (name && name !== "Unknown") userSet.add(name);
		});
		return Array.from(userSet).sort();
	}, [allUsers, chatHistories]);

	// Build chat type options (General Prompt + unique Doctor Types)
	const chatTypes = useMemo(() => {
		const list: ChatTypeOption[] = [
			{ value: "GENERAL_ASSISTANT", label: "General Prompt (Staff)" },
		];
		const doctorTypesSet = new Set<string>();
		allUsers?.forEach((u) => {
			if (u.dr_type) doctorTypesSet.add(u.dr_type);
		});
		chatHistories?.forEach((h) => {
			if (h.doctor_type) doctorTypesSet.add(h.doctor_type);
		});

		doctorTypesSet.forEach((dt) => {
			list.push({ value: dt, label: `Doctor - ${dt}` });
		});

		return list;
	}, [allUsers, chatHistories]);

	const filteredData = useMemo(() => {
		return (
			chatHistories?.filter((item: ChatHistoryResponse) => {
				if (item.messages === 0 && !item.query) return false;

				// Filter by User
				if (userFilter !== "ALL") {
					const itemName = item.user_name || item.doctor;
					if (itemName !== userFilter) return false;
				}

				// Filter by Chat / Doctor Type
				if (chatTypeFilter !== "ALL") {
					if (chatTypeFilter === "GENERAL_ASSISTANT") {
						const isGeneral =
							item.session_type === "GENERAL_ASSISTANT" ||
							(!item.branch_id && item.branch === "General Assistant") ||
							item.user_type === "STAFF";
						if (!isGeneral) return false;
					} else {
						if (!item.doctor_type || item.doctor_type !== chatTypeFilter) return false;
					}
				}

				// Filter by Date Range
				if (dateRange?.from) {
					const itemDate = new Date(item.created_at);
					const fromDate = new Date(dateRange.from);
					fromDate.setHours(0, 0, 0, 0);
					if (itemDate < fromDate) return false;

					const toDate = dateRange.to ? new Date(dateRange.to) : new Date(dateRange.from);
					toDate.setHours(23, 59, 59, 999);
					if (itemDate > toDate) return false;
				}

				// Search Query
				if (debouncedSearch.trim()) {
					const q = debouncedSearch.toLowerCase();
					const matchDoctor = item.doctor?.toLowerCase().includes(q);
					const matchUserName = item.user_name?.toLowerCase().includes(q);
					const matchQuery = item.query?.toLowerCase().includes(q);
					const matchSummary = item.summary?.toLowerCase().includes(q);
					const matchBranch = item.branch?.toLowerCase().includes(q);
					const matchType = item.session_type?.toLowerCase().includes(q);
					if (
						!matchDoctor &&
						!matchUserName &&
						!matchQuery &&
						!matchSummary &&
						!matchBranch &&
						!matchType
					) {
						return false;
					}
				}
				return true;
			}) || []
		);
	}, [chatHistories, userFilter, chatTypeFilter, dateRange, debouncedSearch]);

	const pagination = usePagination({ items: filteredData, initialPageSize: 10 });

	const hasActiveFilters = Boolean(
		userFilter !== "ALL" ||
		chatTypeFilter !== "ALL" ||
		dateRange !== undefined ||
		searchQuery.trim() !== "",
	);

	const handleResetFilters = () => {
		setUserFilter("ALL");
		setChatTypeFilter("ALL");
		setDateRange(undefined);
		setSearchQuery("");
	};

	return {
		// Data state
		isLoading,
		isError,
		filteredData,
		users,
		chatTypes,
		hasActiveFilters,

		// Filters
		userFilter,
		setUserFilter,
		chatTypeFilter,
		setChatTypeFilter,
		dateRange,
		setDateRange,
		searchQuery,
		setSearchQuery,
		handleResetFilters,

		// Pagination
		pagination,
	};
}
