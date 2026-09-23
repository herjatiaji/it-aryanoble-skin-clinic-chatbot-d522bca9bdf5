export type UserType = "STAFF" | "DOCTOR";

export interface RoleResponse {
  id: string;
  name: string;
}

export interface AccessResponse {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
}

export interface RoleDetailResponse {
  id: string;
  name: string;
  accesses: string[];
  user_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface RoleCreatePayload {
  name: string;
  accesses: string[];
}

export interface RoleUpdatePayload {
  name?: string;
  accesses?: string[];
}

export interface BranchResponse {
  id: string;
  external_id?: number;
  name: string;
  code?: string;
  ecosystem?: string;
  address?: string;
  latitude?: string;
  longitude?: string;
  token_limit?: number;
  tokens_used?: number;
  has_custom_limit?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CategoryResponse {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UserBase {
  name: string;
  email?: string | null;
}

export interface UserCreateStaff extends UserBase {
  email: string;
  password: string;
  roles?: string[]; // Defaults to ["Staff"] in backend
}

export interface UserCreateDoctor extends UserBase {
  cis_id: number;
  token_limit?: number;
  employee_id?: string;
  dr_type?: string;
  user_type_code?: string;
  ecosystem?: string;
  branches?: string[]; // UUID strings
  categories?: string[]; // UUID strings
}

export interface StaffUpdate {
  email?: string;
  name?: string;
  password?: string;
  status?: string;
}

export interface DoctorUpdate {
  token_limit?: number;
  status?: string;
  employee_id?: string;
  dr_type?: string;
  user_type_code?: string;
  ecosystem?: string;
}

export interface UserUpdateRoles {
  roles: string[];
}

export interface UserUpdateBranches {
  branches: string[];
}

export interface UserUpdateCategories {
  categories: string[];
}

export interface UserResponse extends UserBase {
  id: string;
  type: UserType;
  cis_id?: number;
  token_limit?: number;
  employee_id?: string;
  dr_type?: string;
  user_type_code?: string;
  ecosystem?: string;
  created_at: string;
  
  status?: string;
  tokens_used?: number;
  roles?: RoleResponse[];
  branches?: BranchResponse[];
  categories?: CategoryResponse[];
}
