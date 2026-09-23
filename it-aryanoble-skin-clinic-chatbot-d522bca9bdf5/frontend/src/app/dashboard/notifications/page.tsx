"use client";

import { NotificationFilterBar } from "./components/notification-filter-bar";
import { NotificationHeader } from "./components/notification-header";
import { NotificationList } from "./components/notification-list";
import { useNotificationsState } from "./hooks/use-notifications-state";

export default function NotificationsPage() {
	const {
		feedbacks,
		isLoading,
		activeTab,
		setActiveTab,
		searchQuery,
		setSearchQuery,
		doctorFilter,
		setDoctorFilter,
		doctorTypeFilter,
		setDoctorTypeFilter,
		doctors,
		doctorTypes,
		unreadCount,
		readCount,
		filteredFeedbacks,
		hasActiveFilters,
		handleResetDropdownFilters,
		handleMarkAllAsRead,
		handleMarkAsRead,
		isMarkingRead,
		pagination,
	} = useNotificationsState();

	return (
		<div className="flex flex-col h-full gap-4 p-6">
			<NotificationHeader
				unreadCount={unreadCount}
				isMarkingRead={isMarkingRead}
				onMarkAllAsRead={handleMarkAllAsRead}
			/>

			<NotificationFilterBar
				activeTab={activeTab}
				onTabChange={setActiveTab}
				searchQuery={searchQuery}
				onSearchChange={setSearchQuery}
				totalCount={feedbacks.length}
				unreadCount={unreadCount}
				readCount={readCount}
				hasActiveFilters={hasActiveFilters}
				onResetFilters={handleResetDropdownFilters}
				doctorFilter={doctorFilter}
				onDoctorFilterChange={setDoctorFilter}
				doctors={doctors}
				doctorTypeFilter={doctorTypeFilter}
				onDoctorTypeFilterChange={setDoctorTypeFilter}
				doctorTypes={doctorTypes}
			/>

			<NotificationList
				isLoading={isLoading}
				totalFilteredCount={filteredFeedbacks.length}
				hasActiveFilters={hasActiveFilters}
				activeTab={activeTab}
				onMarkAsRead={handleMarkAsRead}
				pagination={pagination}
			/>
		</div>
	);
}
