export interface AccessResponse {
	id: string;
	name: string;
	description: string | null;
}

export interface RoleDetailResponse {
	id: string;
	name: string;
	accesses: string[];
	user_count: number;
	created_at: string;
	updated_at: string | null;
}

export interface RoleCreatePayload {
	name: string;
	accesses: string[];
}

export interface RoleUpdatePayload {
	name?: string;
	accesses?: string[];
}
