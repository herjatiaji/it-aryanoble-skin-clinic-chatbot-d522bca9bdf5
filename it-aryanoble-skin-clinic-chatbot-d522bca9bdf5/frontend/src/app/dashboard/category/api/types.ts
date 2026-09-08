export interface CategoryBase {
  name: string;
  description?: string | null;
}

export type CategoryCreate = CategoryBase;

export interface CategoryUpdate {
  name?: string | null;
  description?: string | null;
}

export interface CategoryResponse extends CategoryBase {
  id: string;
  created_at: string;
  updated_at: string;
}
