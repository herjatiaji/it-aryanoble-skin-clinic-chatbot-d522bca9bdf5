export interface FeedbackNotification {
	id: string;
	doctor: string;
	doctor_type?: string | null;
	branch: string;
	query?: string;
	summary?: string;
	rating: "GOOD" | "BAD" | null;
	feedback: string | null;
	has_data_issue: boolean;
	is_feedback_read: boolean;
	updated_at: string;
	created_at?: string;
}

