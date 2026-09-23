export interface ConfigResponse {
	key: string;
	value: string;
}

export interface GlobalMonthlyUsageResponse {
	year_month: string;
	tokens_used: number;
	token_limit?: number | null;
	remaining?: number | null;
	percentage?: number | null;
	is_global_active: boolean;
}

export interface ConfigUpdate {
	value: string;
}

export interface BranchBase {
	name: string;
	token_limit: number;
}

export interface BranchUpdate {
	token_limit: number;
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

	doctors: BranchDoctorResponse[];
}
