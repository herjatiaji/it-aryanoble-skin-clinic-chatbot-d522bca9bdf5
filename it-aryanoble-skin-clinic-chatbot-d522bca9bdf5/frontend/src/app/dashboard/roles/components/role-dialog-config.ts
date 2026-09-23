export interface PermissionAction {
	id: "create" | "read" | "update" | "delete";
	label: string;
	key: string;
}

export interface ModuleConfig {
	id: string;
	name: string;
	actions: PermissionAction[];
}

export const MODULES_CONFIG: ModuleConfig[] = [
	{
		id: "knowledge",
		name: "Knowledge Base",
		actions: [
			{ id: "create", label: "Create", key: "knowledge:create" },
			{ id: "read", label: "Read", key: "knowledge:read" },
			{ id: "update", label: "Update", key: "knowledge:update" },
			{ id: "delete", label: "Delete", key: "knowledge:delete" },
		],
	},
	{
		id: "chats",
		name: "Chat History",
		actions: [
			{ id: "create", label: "Create", key: "chats:create" },
			{ id: "read", label: "Read", key: "chats:read" },
			{ id: "update", label: "Update", key: "chats:update" },
			{ id: "delete", label: "Delete", key: "chats:delete" },
		],
	},
	{
		id: "categories",
		name: "Category",
		actions: [
			{ id: "create", label: "Create", key: "categories:create" },
			{ id: "read", label: "Read", key: "categories:read" },
			{ id: "update", label: "Update", key: "categories:update" },
			{ id: "delete", label: "Delete", key: "categories:delete" },
		],
	},
	{
		id: "branches",
		name: "Branch",
		actions: [
			{ id: "create", label: "Create", key: "branches:create" },
			{ id: "read", label: "Read", key: "branches:read" },
			{ id: "update", label: "Update", key: "branches:update" },
			{ id: "delete", label: "Delete", key: "branches:delete" },
		],
	},
	{
		id: "users",
		name: "User",
		actions: [
			{ id: "create", label: "Create", key: "users:create" },
			{ id: "read", label: "Read", key: "users:read" },
			{ id: "update", label: "Update", key: "users:update" },
			{ id: "delete", label: "Delete", key: "users:delete" },
		],
	},
	{
		id: "roles",
		name: "Role",
		actions: [
			{ id: "create", label: "Create", key: "roles:create" },
			{ id: "read", label: "Read", key: "roles:read" },
			{ id: "update", label: "Update", key: "roles:update" },
			{ id: "delete", label: "Delete", key: "roles:delete" },
		],
	},
	{
		id: "configuration",
		name: "Configuration",
		actions: [
			{ id: "create", label: "Create", key: "configuration:create" },
			{ id: "read", label: "Read", key: "configuration:read" },
			{ id: "update", label: "Update", key: "configuration:update" },
			{ id: "delete", label: "Delete", key: "configuration:delete" },
		],
	},
	{
		id: "notifications",
		name: "Notification",
		actions: [
			{ id: "create", label: "Create", key: "notifications:create" },
			{ id: "read", label: "Read", key: "notifications:read" },
			{ id: "update", label: "Update", key: "notifications:update" },
			{ id: "delete", label: "Delete", key: "notifications:delete" },
		],
	},
];

// Helper to normalize raw backend accesses to UI keys
export function normalizeAccessesToUi(rawAccesses: string[], roleName?: string): string[] {
	if (roleName?.toUpperCase() === "ADMIN") {
		return MODULES_CONFIG.flatMap((m) => m.actions.map((a) => a.key));
	}

	const result = new Set<string>();
	rawAccesses.forEach((acc) => {
		result.add(acc);
		// If backend returns umbrella 'write' access, expand to UI actions
		if (acc === "knowledge:write") {
			result.add("knowledge:create");
			result.add("knowledge:update");
		}
		if (acc === "chats:read") {
			result.add("chats:create");
			result.add("chats:read");
			result.add("chats:update");
			result.add("chats:delete");
		}
		if (acc === "users:write") {
			result.add("users:create");
			result.add("users:update");
			result.add("users:delete");
		}
		if (acc === "roles:write") {
			result.add("roles:create");
			result.add("roles:update");
			result.add("roles:delete");
		}
		if (acc === "branches:write") {
			result.add("branches:create");
			result.add("branches:update");
			result.add("branches:delete");
		}
		if (acc === "categories:write") {
			result.add("categories:create");
			result.add("categories:update");
			result.add("categories:delete");
		}
		if (acc === "configuration:write") {
			result.add("configuration:create");
			result.add("configuration:update");
			result.add("configuration:delete");
		}
		if (acc === "notifications:write") {
			result.add("notifications:create");
			result.add("notifications:update");
			result.add("notifications:delete");
		}
	});
	return Array.from(result);
}

// Helper to expand UI keys to backend accesses (including legacy umbrella keys)
export function expandUiAccessesToBackend(uiAccesses: string[]): string[] {
	const result = new Set<string>(uiAccesses);

	// Add umbrella 'write' keys if any write-like action is selected
	if (uiAccesses.some((k) => k === "knowledge:create" || k === "knowledge:update")) {
		result.add("knowledge:write");
	}
	if (uiAccesses.some((k) => k.startsWith("users:") && k !== "users:read")) {
		result.add("users:write");
	}
	if (uiAccesses.some((k) => k.startsWith("roles:") && k !== "roles:read")) {
		result.add("roles:write");
	}
	if (uiAccesses.some((k) => k.startsWith("branches:") && k !== "branches:read")) {
		result.add("branches:write");
	}
	if (uiAccesses.some((k) => k.startsWith("categories:") && k !== "categories:read")) {
		result.add("categories:write");
	}
	if (uiAccesses.some((k) => k.startsWith("configuration:") && k !== "configuration:read")) {
		result.add("configuration:write");
	}
	if (uiAccesses.some((k) => k.startsWith("notifications:") && k !== "notifications:read")) {
		result.add("notifications:write");
	}

	return Array.from(result);
}
