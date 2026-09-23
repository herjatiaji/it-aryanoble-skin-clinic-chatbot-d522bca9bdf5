import { api } from "@/lib/axios";
import { FeedbackNotification } from "./types";

export async function getFeedbacks(): Promise<FeedbackNotification[]> {
	const res = await api.get<FeedbackNotification[]>("/chats/feedback");
	return res.data;
}

export async function markFeedbacksAsRead(sessionIds: string[]): Promise<void> {
	await api.put("/chats/feedback/read", { session_ids: sessionIds });
}
