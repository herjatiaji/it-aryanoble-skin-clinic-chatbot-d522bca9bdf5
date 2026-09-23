export interface BranchBase {
	name: string;
	token_limit: number;
}

export interface BranchUpdate {
	token_limit?: number;
	has_custom_limit?: boolean;
	reset_to_global?: boolean;
}

export interface BranchDoctorResponse {
	id: string;
	name: string;
	speciality: string;
	tokensLeft: number;
	tokens_used?: number;
	status: string;
	maxTokens: number;
	employee_id?: string;
	dr_type?: string;
	user_type_code?: string;
	ecosystem?: string;
}

export interface BranchResponse extends BranchBase {
	id: string;
	external_id?: number;
	code?: string;
	ecosystem?: string;
	created_at: string;
	updated_at: string;
	tokensMonth?: number;
	used: number;
	remaining: number;
	has_custom_limit?: boolean;
	doctors: BranchDoctorResponse[];
}
