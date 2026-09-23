import { useEffect, useState } from "react";
import { RoleDetailResponse } from "../api/types";
import {
	MODULES_CONFIG,
	ModuleConfig,
	expandUiAccessesToBackend,
	normalizeAccessesToUi,
} from "../components/role-dialog-config";
import { useCreateRole, useDeleteRole, useUpdateRole } from "./use-roles";

interface UseRoleFormProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	role: RoleDetailResponse | null;
	mode: "add" | "edit";
}

export function useRoleForm({ isOpen, onOpenChange, role, mode }: UseRoleFormProps) {
	const [name, setName] = useState("");
	const [selectedUiKeys, setSelectedUiKeys] = useState<string[]>([]);
	const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);

	const createRole = useCreateRole();
	const updateRole = useUpdateRole();
	const deleteRole = useDeleteRole();

	useEffect(() => {
		if (isOpen) {
			const timer = setTimeout(() => {
				if (mode === "edit" && role) {
					setName(role.name || "");
					setSelectedUiKeys(normalizeAccessesToUi(role.accesses || [], role.name));
				} else {
					setName("");
					setSelectedUiKeys([]);
				}
				setIsDeleteDialogOpen(false);
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [isOpen, role, mode]);

	const totalModules = MODULES_CONFIG.length;
	const isAllSelected =
		MODULES_CONFIG.filter((m) => m.actions.some((a) => selectedUiKeys.includes(a.key))).length ===
		totalModules;

	const toggleGlobalSelectAll = () => {
		if (isAllSelected) {
			setSelectedUiKeys([]);
		} else {
			const allKeys = MODULES_CONFIG.flatMap((m) => m.actions.map((a) => a.key));
			setSelectedUiKeys(allKeys);
		}
	};

	const toggleModule = (module: ModuleConfig) => {
		const moduleKeys = module.actions.map((a) => a.key);
		const allSelected = moduleKeys.every((k) => selectedUiKeys.includes(k));

		if (allSelected) {
			setSelectedUiKeys((prev) => prev.filter((k) => !moduleKeys.includes(k)));
		} else {
			setSelectedUiKeys((prev) => Array.from(new Set([...prev, ...moduleKeys])));
		}
	};

	const toggleAction = (
		module: ModuleConfig,
		actionId: "create" | "read" | "update" | "delete",
		actionKey: string,
	) => {
		setSelectedUiKeys((prev) => {
			const isCurrentlyChecked = prev.includes(actionKey);
			const readActionKey = module.actions.find((a) => a.id === "read")?.key;
			const moduleActionKeys = module.actions.map((a) => a.key);

			if (isCurrentlyChecked) {
				// UNCHECKING: If unchecking READ, uncheck all actions in this module
				if (actionId === "read") {
					return prev.filter((k) => !moduleActionKeys.includes(k));
				} else {
					return prev.filter((k) => k !== actionKey);
				}
			} else {
				// CHECKING: If checking Create, Update, or Delete, automatically ensure Read is also checked
				const newKeys = new Set(prev);
				newKeys.add(actionKey);
				if (readActionKey) {
					newKeys.add(readActionKey);
				}
				return Array.from(newKeys);
			}
		});
	};

	const handleSave = () => {
		const cleanName = name.trim().toUpperCase();
		if (!cleanName) return;

		const backendAccesses = expandUiAccessesToBackend(selectedUiKeys);

		if (mode === "add") {
			createRole.mutate(
				{ name: cleanName, accesses: backendAccesses },
				{
					onSuccess: () => onOpenChange(false),
				},
			);
		} else if (mode === "edit" && role) {
			updateRole.mutate(
				{
					roleId: role.id,
					data: { name: cleanName, accesses: backendAccesses },
				},
				{
					onSuccess: () => onOpenChange(false),
				},
			);
		}
	};

	const handleDeleteClick = () => {
		if (!role || role.name.toUpperCase() === "ADMIN") return;
		setIsDeleteDialogOpen(true);
	};

	const handleConfirmDelete = () => {
		if (!role) return;
		deleteRole.mutate(role.id, {
			onSuccess: () => {
				setIsDeleteDialogOpen(false);
				onOpenChange(false);
			},
		});
	};

	const isPending = createRole.isPending || updateRole.isPending || deleteRole.isPending;
	const isSystemAdmin = mode === "edit" && role?.name.toUpperCase() === "ADMIN";

	return {
		name,
		setName,
		selectedUiKeys,
		isDeleteDialogOpen,
		setIsDeleteDialogOpen,
		toggleGlobalSelectAll,
		toggleModule,
		toggleAction,
		handleSave,
		handleDeleteClick,
		handleConfirmDelete,
		isPending,
		isSystemAdmin,
	};
}
