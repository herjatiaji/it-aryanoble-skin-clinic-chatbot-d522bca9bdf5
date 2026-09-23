import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useConfigs, useUpdateConfig } from "./use-config";

export interface PendingSaveState {
	key: "GLOBAL_TOKEN_THRESHOLD" | "GLOBAL_TOKEN_LIMIT" | "TOKEN_LIMIT_SPKK" | "TOKEN_LIMIT_GP";
	activeKey: "GLOBAL_THRESHOLD_ACTIVE" | "GLOBAL_BRANCH_LIMIT_ACTIVE" | "GLOBAL_SPKK_LIMIT_ACTIVE" | "GLOBAL_GP_LIMIT_ACTIVE";
	title: string;
	description: string;
	value: string;
	setter: (val: boolean) => void;
}

export interface PendingDeactivateState {
	key: "GLOBAL_TOKEN_THRESHOLD" | "GLOBAL_TOKEN_LIMIT" | "TOKEN_LIMIT_SPKK" | "TOKEN_LIMIT_GP";
	activeKey: "GLOBAL_THRESHOLD_ACTIVE" | "GLOBAL_BRANCH_LIMIT_ACTIVE" | "GLOBAL_SPKK_LIMIT_ACTIVE" | "GLOBAL_GP_LIMIT_ACTIVE";
	title: string;
	description: string;
}

const ACTIVE_KEY_MAP: Record<
	"GLOBAL_TOKEN_THRESHOLD" | "GLOBAL_TOKEN_LIMIT" | "TOKEN_LIMIT_SPKK" | "TOKEN_LIMIT_GP",
	"GLOBAL_THRESHOLD_ACTIVE" | "GLOBAL_BRANCH_LIMIT_ACTIVE" | "GLOBAL_SPKK_LIMIT_ACTIVE" | "GLOBAL_GP_LIMIT_ACTIVE"
> = {
	GLOBAL_TOKEN_THRESHOLD: "GLOBAL_THRESHOLD_ACTIVE",
	GLOBAL_TOKEN_LIMIT: "GLOBAL_BRANCH_LIMIT_ACTIVE",
	TOKEN_LIMIT_SPKK: "GLOBAL_SPKK_LIMIT_ACTIVE",
	TOKEN_LIMIT_GP: "GLOBAL_GP_LIMIT_ACTIVE",
};

export function useTokenConfigState() {
	const { data: configs, isLoading } = useConfigs();
	const updateConfig = useUpdateConfig();

	const isGlobalLimitActive =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT_ACTIVE")?.value === "true";
	const isThresholdActive =
		configs?.find((c) => c.key === "GLOBAL_THRESHOLD_ACTIVE")?.value === "true";
	const isBranchActive =
		configs?.find((c) => c.key === "GLOBAL_BRANCH_LIMIT_ACTIVE")?.value === "true";
	const isSpdveActive =
		configs?.find((c) => c.key === "GLOBAL_SPKK_LIMIT_ACTIVE")?.value === "true";
	const isGpPlusActive =
		configs?.find((c) => c.key === "GLOBAL_GP_LIMIT_ACTIVE")?.value === "true";

	const globalThreshold =
		configs?.find((c) => c.key === "GLOBAL_TOKEN_THRESHOLD")?.value || "1000000";
	const branchTokenLimit = configs?.find((c) => c.key === "GLOBAL_TOKEN_LIMIT")?.value || "3000000";
	const spdveLimit = configs?.find((c) => c.key === "TOKEN_LIMIT_SPKK")?.value || "500000";
	const gpPlusLimit = configs?.find((c) => c.key === "TOKEN_LIMIT_GP")?.value || "250000";

	const [isActive, setIsActive] = useState(false);

	// Per-field value states
	const [thresholdAmount, setThresholdAmount] = useState("1000000");
	const [branchAmount, setBranchAmount] = useState("3000000");
	const [spdveAmount, setSpdveAmount] = useState("500000");
	const [gpPlusAmount, setGpPlusAmount] = useState("250000");

	// Per-field edit states
	const [editingThreshold, setEditingThreshold] = useState(false);
	const [editingBranch, setEditingBranch] = useState(false);
	const [editingSpdve, setEditingSpdve] = useState(false);
	const [editingGpPlus, setEditingGpPlus] = useState(false);

	const [savingKey, setSavingKey] = useState<string | null>(null);
	const [deactivatingKey, setDeactivatingKey] = useState<string | null>(null);
	const [showWarning, setShowWarning] = useState(false);
	const warningTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);

	// Toggle Confirmation State
	const [toggleModalOpen, setToggleModalOpen] = useState(false);
	const [pendingToggleActive, setPendingToggleActive] = useState<boolean | null>(null);

	// Save Confirmation State
	const [saveModalOpen, setSaveModalOpen] = useState(false);
	const [pendingSave, setPendingSave] = useState<PendingSaveState | null>(null);

	// Deactivate Confirmation State
	const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
	const [pendingDeactivate, setPendingDeactivate] = useState<PendingDeactivateState | null>(null);

	// Sync state when configs load
	useEffect(() => {
		if (configs) {
			const timer = setTimeout(() => {
				setIsActive(isGlobalLimitActive);
				setThresholdAmount(globalThreshold);
				setBranchAmount(branchTokenLimit);
				setSpdveAmount(spdveLimit);
				setGpPlusAmount(gpPlusLimit);
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [configs, isGlobalLimitActive, globalThreshold, branchTokenLimit, spdveLimit, gpPlusLimit]);

	const handleInitiateSave = (
		key: "GLOBAL_TOKEN_THRESHOLD" | "GLOBAL_TOKEN_LIMIT" | "TOKEN_LIMIT_SPKK" | "TOKEN_LIMIT_GP",
		title: string,
		description: string,
		value: string,
		setter: (val: boolean) => void,
	) => {
		const activeKey = ACTIVE_KEY_MAP[key];
		setPendingSave({ key, activeKey, title, description, value, setter });
		setSaveModalOpen(true);
	};

	const handleConfirmSave = async () => {
		if (!pendingSave) return;
		const { key, activeKey, value, setter } = pendingSave;
		try {
			setSavingKey(key);
			// 1. Update the token amount configuration
			await updateConfig.mutateAsync({ key, data: { value } });
			// 2. Activate this specific granular configuration rule
			await updateConfig.mutateAsync({ key: activeKey, data: { value: "true" } });

			setter(false);
			setShowWarning(true);
			if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current);
			warningTimeoutRef.current = setTimeout(() => {
				setShowWarning(false);
			}, 5000);
			toast.success("Configuration saved and activated successfully!");
		} catch {
			toast.error("Failed to update token configuration.");
		} finally {
			setSavingKey(null);
			setPendingSave(null);
		}
	};

	const handleInitiateDeactivate = (
		key: "GLOBAL_TOKEN_THRESHOLD" | "GLOBAL_TOKEN_LIMIT" | "TOKEN_LIMIT_SPKK" | "TOKEN_LIMIT_GP",
		title: string,
		description: string,
	) => {
		const activeKey = ACTIVE_KEY_MAP[key];
		setPendingDeactivate({ key, activeKey, title, description });
		setDeactivateModalOpen(true);
	};

	const handleConfirmDeactivate = async () => {
		if (!pendingDeactivate) return;
		const { key, activeKey } = pendingDeactivate;
		try {
			setDeactivatingKey(key);
			// Deactivate this specific granular configuration rule
			await updateConfig.mutateAsync({ key: activeKey, data: { value: "false" } });

			setShowWarning(true);
			if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current);
			warningTimeoutRef.current = setTimeout(() => {
				setShowWarning(false);
			}, 5000);
			toast.success("Configuration rule has been deactivated.");
		} catch {
			toast.error("Failed to deactivate configuration rule.");
		} finally {
			setDeactivatingKey(null);
			setPendingDeactivate(null);
		}
	};

	const handleInitiateToggle = (checked: boolean) => {
		setPendingToggleActive(checked);
		setToggleModalOpen(true);
	};

	const handleConfirmToggle = () => {
		if (pendingToggleActive === null) return;
		const checked = pendingToggleActive;
		setIsActive(checked);

		setShowWarning(true);
		if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current);
		warningTimeoutRef.current = setTimeout(() => {
			setShowWarning(false);
		}, 5000);

		if (checked) {
			// When turning ON: Global Token Threshold is immediately active, only branch and doctor types are on hold in edit mode
			setEditingThreshold(false);
			setEditingBranch(true);
			setEditingSpdve(true);
			setEditingGpPlus(true);
		} else {
			// When turning OFF: Close edit mode on all sub-settings
			setEditingThreshold(false);
			setEditingBranch(false);
			setEditingSpdve(false);
			setEditingGpPlus(false);
		}

		updateConfig.mutate(
			{ key: "GLOBAL_TOKEN_LIMIT_ACTIVE", data: { value: checked.toString() } },
			{
				onSuccess: () => {
					setPendingToggleActive(null);
					if (checked) {
						toast.success("Global token configuration activated. Global threshold is active.");
					} else {
						toast.success("All global token configurations have been deactivated.");
					}
				},
				onError: () => {
					setIsActive(!checked);
					setPendingToggleActive(null);
				},
			},
		);
	};

	return {
		isLoading,
		isPending: updateConfig.isPending,
		isActive,
		isThresholdActive: isActive && isThresholdActive,
		isBranchActive: isActive && isBranchActive,
		isSpdveActive: isActive && isSpdveActive,
		isGpPlusActive: isActive && isGpPlusActive,
		thresholdAmount,
		setThresholdAmount,
		globalThreshold,
		editingThreshold,
		setEditingThreshold,
		branchAmount,
		setBranchAmount,
		branchTokenLimit,
		editingBranch,
		setEditingBranch,
		spdveAmount,
		setSpdveAmount,
		spdveLimit,
		editingSpdve,
		setEditingSpdve,
		gpPlusAmount,
		setGpPlusAmount,
		gpPlusLimit,
		editingGpPlus,
		setEditingGpPlus,
		savingKey,
		deactivatingKey,
		showWarning,
		toggleModalOpen,
		setToggleModalOpen,
		pendingToggleActive,
		setPendingToggleActive,
		saveModalOpen,
		setSaveModalOpen,
		pendingSave,
		setPendingSave,
		deactivateModalOpen,
		setDeactivateModalOpen,
		pendingDeactivate,
		setPendingDeactivate,
		handleInitiateToggle,
		handleConfirmToggle,
		handleInitiateSave,
		handleConfirmSave,
		handleInitiateDeactivate,
		handleConfirmDeactivate,
	};
}


