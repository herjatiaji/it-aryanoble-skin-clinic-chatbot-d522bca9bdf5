import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chatHistoryKeys } from "../../chat-history/api/keys";
import { getFeedbacks, markFeedbacksAsRead } from "../api";
import { NOTIFICATION_KEYS } from "../api/keys";
import { FeedbackNotification } from "../api/types";

export function useNotifications() {
	return useQuery<FeedbackNotification[]>({
		queryKey: NOTIFICATION_KEYS.lists(),
		queryFn: getFeedbacks,
	});
}

export function useMarkNotificationsAsRead() {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: (sessionIds: string[]) => markFeedbacksAsRead(sessionIds),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEYS.all });
			queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all });
		},
	});
}
