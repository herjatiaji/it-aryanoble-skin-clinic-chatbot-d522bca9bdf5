export interface ApiError {
  detail: string | Array<{ loc: (string | number)[]; msg: string; type: string }>;
}

export interface UserResponse {
  id: string;
  type: "STAFF" | "DOCTOR" | "ADMIN";
  email: string;
  name: string;
  cis_id: string | null;
  token_limit: number | null;
  created_at: string;
  status: "Active" | "Inactive" | "Warning";
  roles: Array<{ id: string; name: string }>;
  accesses: string[];
  branches: Array<Record<string, unknown>>;
  categories: Array<Record<string, unknown>>;
  tokens_used: number;
}
