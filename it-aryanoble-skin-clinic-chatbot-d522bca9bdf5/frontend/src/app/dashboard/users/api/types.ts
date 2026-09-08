export type UserType = "STAFF" | "DOCTOR";

export interface RoleResponse {
  id: string;
  name: string;
}

export interface BranchResponse {
  id: string;
  name: string;
  address?: string;
  latitude?: string;
  longitude?: string;
  image_url?: string;
  token_limit?: number;
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
  email: string;
  name: string;
}

export interface UserCreateStaff extends UserBase {
  password: string;
  roles?: string[]; // Defaults to ["Staff"] in backend
}

export interface UserCreateDoctor extends UserBase {
  cis_id: string;
  token_limit?: number;
  employee_id?: string;
  dr_type?: string;
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
  cis_id?: string;
  token_limit?: number;
  employee_id?: string;
  dr_type?: string;
  ecosystem?: string;
  created_at: string;
  
  status?: string;
  tokens_used?: number;
  roles?: RoleResponse[];
  branches?: BranchResponse[];
  categories?: CategoryResponse[];
}
