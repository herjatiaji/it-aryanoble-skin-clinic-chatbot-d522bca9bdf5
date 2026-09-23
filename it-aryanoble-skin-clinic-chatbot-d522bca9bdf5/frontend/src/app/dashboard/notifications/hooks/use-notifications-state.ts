import { usePagination } from "@/hooks/use-pagination";
import { useMemo, useState } from "react";
import { useMarkNotificationsAsRead, useNotifications } from "./use-notifications";

export type NotificationFilterTab = "all" | "unread" | "read";

export function useNotificationsState() {
	const [activeTab, setActiveTab] = useState<NotificationFilterTab>("all");
	const [searchQuery, setSearchQuery] = useState<string>("");
	const [doctorFilter, setDoctorFilter] = useState<string>("ALL");
	const [doctorTypeFilter, setDoctorTypeFilter] = useState<string>("ALL");

	const { data: feedbacks = [], isLoading } = useNotifications();
	const markAsReadMutation = useMarkNotificationsAsRead();

	// Extract unique doctors and doctor types
	const doctors = useMemo(() => {
		const unique = new Set<string>();
		feedbacks.forEach((f) => {
			if (f.doctor && f.doctor !== "Unknown") {
				unique.add(f.doctor);
			}
		});
		return Array.from(unique);
	}, [feedbacks]);

	const doctorTypes = useMemo(() => {
		const unique = new Set<string>();
		feedbacks.forEach((f) => {
			if (f.doctor_type) {
				unique.add(f.doctor_type);
			}
		});
		return Array.from(unique);
	}, [feedbacks]);

	const unreadCount = useMemo(
		() => feedbacks.filter((f) => !f.is_feedback_read).length,
		[feedbacks],
	);

	const readCount = useMemo(() => feedbacks.filter((f) => f.is_feedback_read).length, [feedbacks]);

	const filteredFeedbacks = useMemo(() => {
		const query = searchQuery.trim().toLowerCase();

		return feedbacks.filter((item) => {
			// Tab filter
			if (activeTab === "unread" && item.is_feedback_read) return false;
			if (activeTab === "read" && !item.is_feedback_read) return false;

			// Doctor filter
			if (doctorFilter !== "ALL" && item.doctor !== doctorFilter) return false;

			// Doctor type filter
			if (doctorTypeFilter !== "ALL" && item.doctor_type !== doctorTypeFilter) return false;

			// Search query filter
			if (query) {
				const doctorMatch = item.doctor?.toLowerCase().includes(query);
				const branchMatch = item.branch?.toLowerCase().includes(query);
				const feedbackMatch = item.feedback?.toLowerCase().includes(query);
				const doctorTypeMatch = item.doctor_type?.toLowerCase().includes(query);
				const idMatch = item.id.toLowerCase().includes(query);
				if (!doctorMatch && !branchMatch && !feedbackMatch && !doctorTypeMatch && !idMatch) {
					return false;
				}
			}

			return true;
		});
	}, [feedbacks, activeTab, doctorFilter, doctorTypeFilter, searchQuery]);

	const pagination = usePagination({ items: filteredFeedbacks, initialPageSize: 10 });

	const hasActiveFilters =
		doctorFilter !== "ALL" || doctorTypeFilter !== "ALL" || searchQuery.trim().length > 0;

	const handleSearchChange = (val: string) => {
		setSearchQuery(val);
		pagination.setPage(1);
	};

	const handleTabChange = (tab: NotificationFilterTab) => {
		setActiveTab(tab);
		pagination.setPage(1);
	};

	const handleDoctorFilterChange = (doctor: string) => {
		setDoctorFilter(doctor);
		pagination.setPage(1);
	};

	const handleDoctorTypeFilterChange = (type: string) => {
		setDoctorTypeFilter(type);
		pagination.setPage(1);
	};

	const handleResetFilters = () => {
		setDoctorFilter("ALL");
		setDoctorTypeFilter("ALL");
		setSearchQuery("");
		pagination.setPage(1);
	};

	const handleMarkAllAsRead = () => {
		const unreadIds = feedbacks.filter((f) => !f.is_feedback_read).map((f) => f.id);
		if (unreadIds.length === 0) return;
		markAsReadMutation.mutate(unreadIds);
	};

	const handleMarkAsRead = (id: string) => {
		markAsReadMutation.mutate([id]);
	};

	return {
		feedbacks,
		isLoading,
		activeTab,
		setActiveTab: handleTabChange,
		searchQuery,
		setSearchQuery: handleSearchChange,
		doctorFilter,
		setDoctorFilter: handleDoctorFilterChange,
		doctorTypeFilter,
		setDoctorTypeFilter: handleDoctorTypeFilterChange,
		doctors,
		doctorTypes,
		unreadCount,
		readCount,
		filteredFeedbacks,
		hasActiveFilters,
		handleResetDropdownFilters: handleResetFilters,
		handleMarkAllAsRead,
		handleMarkAsRead,
		isMarkingRead: markAsReadMutation.isPending,
		pagination,
	};
}
