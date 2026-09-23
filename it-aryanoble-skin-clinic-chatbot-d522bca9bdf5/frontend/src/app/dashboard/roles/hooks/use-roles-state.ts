import { useDebounce } from "@/hooks/use-debounce";
import { usePagination } from "@/hooks/use-pagination";
import { useTableSort } from "@/hooks/use-table-sort";
import { useMemo, useState } from "react";
import { RoleDetailResponse } from "../api/types";
import { useRoles } from "./use-roles";

export function useRolesState() {
	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 300);
	const [selectedRole, setSelectedRole] = useState<RoleDetailResponse | null>(null);
	const [roleDialogMode, setRoleDialogMode] = useState<"add" | "edit">("add");
	const [isRoleDialogOpen, setIsRoleDialogOpen] = useState(false);

	const { data: rolesData = [], isLoading } = useRoles();
	const { sortKey, sortOrder, handleSort, sortItems } = useTableSort({
		initialSortKey: "name",
		initialSortOrder: "asc",
	});

	const handleAddRole = () => {
		setSelectedRole(null);
		setRoleDialogMode("add");
		setIsRoleDialogOpen(true);
	};

	const handleEditRole = (role: RoleDetailResponse) => {
		setSelectedRole(role);
		setRoleDialogMode("edit");
		setIsRoleDialogOpen(true);
	};

	const selectedRoleLive = rolesData.find((r) => r.id === selectedRole?.id) || selectedRole;

	// Filtered roles based on search query
	const filteredRoles = useMemo(() => {
		let result = rolesData;
		if (debouncedSearch.trim()) {
			const q = debouncedSearch.toLowerCase();
			result = rolesData.filter(
				(r) =>
					r.name.toLowerCase().includes(q) || r.accesses?.some((a) => a.toLowerCase().includes(q)),
			);
		}
		return sortItems<RoleDetailResponse>(result);
	}, [rolesData, debouncedSearch, sortItems]);

	const pagination = usePagination({ items: filteredRoles, initialPageSize: 10 });

	const handleClearSearch = () => {
		setSearchQuery("");
	};

	return {
		searchQuery,
		setSearchQuery,
		handleClearSearch,
		selectedRoleLive,
		roleDialogMode,
		isRoleDialogOpen,
		setIsRoleDialogOpen,
		handleAddRole,
		handleEditRole,
		isLoading,
		rolesData,
		filteredRoles,
		pagination,
		sortKey,
		sortOrder,
		handleSort,
	};
}
