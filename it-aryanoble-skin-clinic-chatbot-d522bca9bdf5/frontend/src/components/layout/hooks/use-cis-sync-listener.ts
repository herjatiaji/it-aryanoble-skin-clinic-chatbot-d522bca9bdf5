"use client";

import { branchKeys } from "@/app/dashboard/branches/api/keys";
import { chatHistoryKeys } from "@/app/dashboard/chat-history/api/keys";
import { NOTIFICATION_KEYS } from "@/app/dashboard/notifications/api/keys";
import { userKeys } from "@/app/dashboard/users/api/keys";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";

export function useCisSyncListener() {
	const queryClient = useQueryClient();

	useEffect(() => {
		let isMounted = true;
		let reconnectTimeout: NodeJS.Timeout | null = null;
		let eventSource: EventSource | null = null;
		const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

		function connect() {
			if (!isMounted) return;

			if (eventSource) {
				eventSource.onerror = null;
				eventSource.close();
				eventSource = null;
			}

			try {
				eventSource = new EventSource(`${apiUrl}/events/sync`);

				eventSource.onmessage = (event) => {
					if (!isMounted) return;

					if (event.data === "sync_completed") {
						queryClient.invalidateQueries({ queryKey: userKeys.all });
						queryClient.invalidateQueries({ queryKey: branchKeys.lists() });
						queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all });
						toast.info("Data refreshed from CIS sync.");
					} else if (event.data === "feedback_submitted") {
						queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEYS.all });
						queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all });
						toast.info("New feedback received.");
					} else {
						try {
							const parsed = JSON.parse(event.data);
							if (parsed.event_type === "KNOWLEDGE_NOT_FOUND") {
								queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEYS.all });
								queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all });
							}
						} catch {
							// Ignore non-json / comment messages
						}
					}
				};

				eventSource.onerror = () => {
					// In EventSource, onerror is an empty event triggered during normal network reconnects or server restarts.
					// Avoid console.error to prevent Next.js Turbopack dev error overlay popups.
					if (!isMounted) return;

					if (eventSource?.readyState === EventSource.CLOSED) {
						eventSource.onerror = null;
						eventSource.close();
						eventSource = null;

						if (!reconnectTimeout) {
							reconnectTimeout = setTimeout(() => {
								reconnectTimeout = null;
								connect();
							}, 5000);
						}
					}
				};
			} catch {
				if (isMounted && !reconnectTimeout) {
					reconnectTimeout = setTimeout(() => {
						reconnectTimeout = null;
						connect();
					}, 5000);
				}
			}
		}

		connect();

		return () => {
			isMounted = false;
			if (reconnectTimeout) {
				clearTimeout(reconnectTimeout);
				reconnectTimeout = null;
			}
			if (eventSource) {
				eventSource.onerror = null;
				eventSource.close();
				eventSource = null;
			}
		};
	}, [queryClient]);
}
