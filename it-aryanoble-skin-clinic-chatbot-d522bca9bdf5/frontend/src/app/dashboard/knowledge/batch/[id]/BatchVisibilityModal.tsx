"use client";

import { useBranches } from "@/app/dashboard/branches/hooks/use-branches";
import { VisibilitySettings as IVisibilitySettings } from "@/app/dashboard/knowledge/api/types";
import { SearchableDropdown } from "@/app/dashboard/knowledge/components/preview/visibility-settings";
import { useUsers } from "@/app/dashboard/users/hooks/use-users";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldContent, FieldGroup, FieldLabel } from "@/components/ui/field";
import { RiCheckLine, RiEyeLine, RiLoader4Line } from "@remixicon/react";
import { useEffect, useMemo, useState } from "react";
import { useUpdateBatchVisibility } from "../../hooks/use-knowledge";

interface BatchVisibilityModalProps {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	batchId: string;
	documentCount?: number;
	initialSettings?: IVisibilitySettings;
	onSuccess?: () => void;
}

export function BatchVisibilityModal({
	isOpen,
	onOpenChange,
	batchId,
	documentCount = 1,
	initialSettings,
	onSuccess,
}: BatchVisibilityModalProps) {
	const { data: branches = [] } = useBranches();
	const { data: doctors = [] } = useUsers("DOCTOR");
	const updateBatchVisibilityMutation = useUpdateBatchVisibility();

	const defaultSettings: IVisibilitySettings = useMemo(
		() =>
			initialSettings || {
				clinics: ["all"],
				doctor_types: ["all"],
				doctors: ["all"],
			},
		[initialSettings],
	);

	const [tempSettings, setTempSettings] = useState<IVisibilitySettings>(defaultSettings);

	useEffect(() => {
		if (isOpen) {
			const timer = setTimeout(() => {
				setTempSettings(
					initialSettings || {
						clinics: ["all"],
						doctor_types: ["all"],
						doctors: ["all"],
					},
				);
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [isOpen, initialSettings]);

	const doctorTypes = useMemo(() => {
		const types = new Set<string>();
		doctors.forEach((doc) => {
			if (doc.dr_type) types.add(doc.dr_type);
		});
		return Array.from(types).sort();
	}, [doctors]);

	const toggleSelection = (key: keyof IVisibilitySettings, value: string) => {
		const current = tempSettings[key] || [];
		const isAllSelected = current.includes("all");

		let updated: string[];
		if (value === "all") {
			updated = isAllSelected ? [] : ["all"];
		} else {
			const withoutAll = current.filter((v) => v !== "all");
			if (withoutAll.includes(value)) {
				updated = withoutAll.filter((v) => v !== value);
			} else {
				updated = [...withoutAll, value];
			}
		}

		setTempSettings((prev) => ({ ...prev, [key]: updated }));
	};

	const formatDisplay = (key: keyof IVisibilitySettings, typeName: string) => {
		const current = tempSettings[key] || ["all"];
		if (current.includes("all")) return `All ${typeName}`;
		if (current.length === 0) return `None selected`;
		if (current.length === 1) {
			if (key === "clinics") return branches.find((b) => b.id === current[0])?.name || current[0];
			if (key === "doctors") return doctors.find((d) => d.id === current[0])?.name || current[0];
			return current[0];
		}
		return `${current.length} ${typeName} Selected`;
	};

	const clinicOptions = useMemo(
		() =>
			branches.map((b) => ({
				label: b.name,
				value: b.id,
				subtitle: b.code ? `Clinic Code: ${b.code}` : undefined,
			})),
		[branches],
	);

	const doctorTypeOptions = useMemo(
		() =>
			doctorTypes.map((t) => ({
				label: t,
				value: t,
			})),
		[doctorTypes],
	);

	const doctorOptions = useMemo(
		() =>
			doctors.map((d) => ({
				label: d.name,
				value: d.id,
				subtitle: d.dr_type ? `Doctor Type: ${d.dr_type}` : undefined,
			})),
		[doctors],
	);

	const handleSave = async () => {
		await updateBatchVisibilityMutation.mutateAsync({
			batchId,
			visibilitySettings: tempSettings,
		});
		onOpenChange(false);
		onSuccess?.();
	};

	const handleCancel = () => {
		onOpenChange(false);
	};

	const isSaveDisabled =
		updateBatchVisibilityMutation.isPending ||
		(tempSettings.clinics && tempSettings.clinics.length === 0) ||
		(tempSettings.doctor_types && tempSettings.doctor_types.length === 0) ||
		(tempSettings.doctors && tempSettings.doctors.length === 0);

	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent className="sm:max-w-md p-0 flex flex-col gap-0 rounded-lg overflow-hidden bg-white border border-gray-200 shadow-none">
				<DialogHeader className="p-4 border-b border-gray-100 flex flex-col gap-0.5">
					<div className="flex items-center gap-2">
						<div className="size-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
							<RiEyeLine className="size-4" />
						</div>
						<div>
							<DialogTitle className="text-base font-semibold text-foreground">
								Batch Visibility Settings
							</DialogTitle>
							<DialogDescription className="text-xs text-muted-foreground">
								Set access limits for all {documentCount} document{documentCount > 1 ? "s" : ""} in
								this batch at once.
							</DialogDescription>
						</div>
					</div>
				</DialogHeader>

				<div className="p-4 flex flex-col gap-4 max-h-[60vh] overflow-y-auto">
					<FieldGroup className="gap-4">
						<Field>
							<FieldLabel className="text-xs font-medium text-zinc-700">Clinic</FieldLabel>
							<FieldContent>
								<SearchableDropdown
									title="Clinic"
									options={clinicOptions}
									selected={tempSettings.clinics || ["all"]}
									onToggle={(val) => toggleSelection("clinics", val)}
									displayText={formatDisplay("clinics", "Clinic")}
								/>
							</FieldContent>
						</Field>

						<Field>
							<FieldLabel className="text-xs font-medium text-zinc-700">Doctor Type</FieldLabel>
							<FieldContent>
								<SearchableDropdown
									title="Doctor Type"
									options={doctorTypeOptions}
									selected={tempSettings.doctor_types || ["all"]}
									onToggle={(val) => toggleSelection("doctor_types", val)}
									displayText={formatDisplay("doctor_types", "Doctor Type")}
								/>
							</FieldContent>
						</Field>

						<Field>
							<FieldLabel className="text-xs font-medium text-zinc-700">Doctor</FieldLabel>
							<FieldContent>
								<SearchableDropdown
									title="Doctor"
									options={doctorOptions}
									selected={tempSettings.doctors || ["all"]}
									onToggle={(val) => toggleSelection("doctors", val)}
									displayText={formatDisplay("doctors", "Doctor")}
								/>
							</FieldContent>
						</Field>
					</FieldGroup>
				</div>

				<DialogFooter className="p-4 border-t border-gray-100 flex items-center justify-end gap-2 bg-zinc-50/50">
					<Button
						type="button"
						variant="outline"
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						onClick={handleCancel}
						disabled={updateBatchVisibilityMutation.isPending}
					>
						Cancel
					</Button>
					<Button
						type="button"
						className="bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg px-4 h-10 gap-1.5 shadow-none transition-colors cursor-pointer disabled:opacity-50"
						disabled={isSaveDisabled}
						onClick={handleSave}
					>
						{updateBatchVisibilityMutation.isPending ? (
							<RiLoader4Line className="size-4 animate-spin" />
						) : (
							<RiCheckLine className="size-4" />
						)}
						{updateBatchVisibilityMutation.isPending ? "Applying..." : "Apply to All"}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
