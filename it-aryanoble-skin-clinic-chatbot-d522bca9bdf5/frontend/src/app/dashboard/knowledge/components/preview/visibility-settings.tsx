import React, { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel, FieldContent, FieldGroup } from "@/components/ui/field";
import {
	RiEyeLine,
	RiEdit2Line,
	RiArrowDownSLine,
	RiCheckLine,
	RiSearchLine,
	RiCloseLine,
} from "@remixicon/react";
import { useBranches } from "@/app/dashboard/branches/hooks/use-branches";
import { useUsers } from "@/app/dashboard/users/hooks/use-users";
import { VisibilitySettings as IVisibilitySettings } from "@/app/dashboard/knowledge/api/types";

export interface DropdownOption {
	label: string;
	value: string;
	subtitle?: string;
}

export interface SearchableDropdownProps {
	title: string;
	options: DropdownOption[];
	selected: string[];
	onToggle: (value: string) => void;
	displayText: string;
}

export function SearchableDropdown({
	title,
	options,
	selected,
	onToggle,
	displayText,
}: SearchableDropdownProps) {
	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 200);
	const [isOpen, setIsOpen] = useState(false);

	const isAllSelected = selected.includes("all");

	const filteredOptions = useMemo(() => {
		if (!debouncedSearch.trim()) return options;
		const q = debouncedSearch.toLowerCase();
		return options.filter(
			(opt) =>
				opt.label.toLowerCase().includes(q) ||
				(opt.subtitle && opt.subtitle.toLowerCase().includes(q)),
		);
	}, [options, debouncedSearch]);

	return (
		<div className="flex flex-col gap-2 w-full">
			<Popover open={isOpen} onOpenChange={setIsOpen}>
				<PopoverTrigger
					render={
						<Button
							type="button"
							variant="outline"
							className="w-full justify-between font-normal text-sm bg-white border-gray-200 focus-visible:ring-blue-500 rounded-lg shadow-none h-10 cursor-pointer"
						>
							<span className="truncate">{displayText}</span>
							<RiArrowDownSLine className="size-4 text-zinc-400 shrink-0" />
						</Button>
					}
				/>
				<PopoverContent
					align="start"
					className="w-80 p-3 flex flex-col gap-2 z-60 bg-white border border-gray-200 shadow-none rounded-lg"
				>
					{/* Search Bar */}
					<div className="relative w-full">
						<RiSearchLine className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-zinc-400 pointer-events-none" />
						<Input
							placeholder={`Search ${title.toLowerCase()}...`}
							value={searchQuery}
							onChange={(e) => setSearchQuery(e.target.value)}
							className="h-8.5 pl-8 pr-8 text-xs bg-zinc-50 border-gray-200 focus-visible:ring-blue-500 rounded-lg shadow-none"
							autoFocus
						/>
						{searchQuery && (
							<button
								type="button"
								onClick={() => setSearchQuery("")}
								className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 cursor-pointer"
							>
								<RiCloseLine className="size-3.5" />
							</button>
						)}
					</div>

					{/* Options List */}
					<div className="flex flex-col gap-0.5 max-h-56 overflow-y-auto overscroll-contain pr-1">
						{/* "All" Option */}
						{!searchQuery && (
							<>
								<div
									className="flex items-center gap-2.5 p-2 hover:bg-zinc-100 rounded-lg cursor-pointer transition-colors"
									onClick={() => onToggle("all")}
								>
									<Checkbox checked={isAllSelected} />
									<div className="flex flex-col min-w-0">
										<span className="text-xs font-semibold text-zinc-900">All {title}</span>
										<span className="text-[11px] text-zinc-500">
											Allow all doctors and branches
										</span>
									</div>
								</div>
								<div className="h-px bg-zinc-200 my-1" />
							</>
						)}

						{filteredOptions.length === 0 ? (
							<div className="py-6 text-center text-xs text-zinc-500">
								No {title.toLowerCase()} found matching &ldquo;{debouncedSearch}&rdquo;
							</div>
						) : (
							filteredOptions.map((opt) => {
								const isChecked = isAllSelected || selected.includes(opt.value);
								return (
									<div
										key={opt.value}
										className="flex items-center gap-2.5 p-2 hover:bg-zinc-100 rounded-lg cursor-pointer transition-colors"
										onClick={() => onToggle(opt.value)}
									>
										<Checkbox checked={isChecked} />
										<div className="flex flex-col min-w-0 flex-1">
											<span className="text-xs font-medium text-zinc-900 truncate">
												{opt.label}
											</span>
											{opt.subtitle && (
												<span className="text-[11px] text-zinc-500 truncate">
													{opt.subtitle}
												</span>
											)}
										</div>
									</div>
								);
							})
						)}
					</div>

					{/* Footer showing count */}
					<div className="pt-1.5 border-t border-zinc-100 flex items-center justify-between text-[11px] text-zinc-500">
						<span>
							{isAllSelected ? `All ${options.length} selected` : `${selected.length} selected`}
						</span>
						{searchQuery && <span>{filteredOptions.length} results</span>}
					</div>
				</PopoverContent>
			</Popover>

			{/* Selected Badges (when specific items are selected) */}
			{!isAllSelected && selected.length > 0 && (
				<div className="flex flex-wrap gap-1.5 mt-1 max-h-24 overflow-y-auto">
					{selected.map((val) => {
						const opt = options.find((o) => o.value === val);
						const label = opt?.label || val;
						return (
							<span
								key={val}
								className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-white text-zinc-800 border border-gray-200 shadow-none"
							>
								<span className="truncate max-w-40">{label}</span>
								<button
									type="button"
									onClick={() => onToggle(val)}
									className="text-zinc-400 hover:text-zinc-700 transition-colors cursor-pointer"
								>
									<RiCloseLine className="size-3.5" />
								</button>
							</span>
						);
					})}
				</div>
			)}
		</div>
	);
}

interface VisibilitySettingsProps {
	settings: IVisibilitySettings;
	onChange: (settings: IVisibilitySettings) => void;
	isEditMode?: boolean;
	showSaveActions?: boolean;
}

export function VisibilitySettings({
	settings,
	onChange,
	isEditMode = false,
}: VisibilitySettingsProps) {
	const { data: branches = [] } = useBranches();
	const { data: doctors = [] } = useUsers("DOCTOR");

	const doctorTypes = useMemo(() => {
		const types = new Set<string>();
		doctors.forEach((doc) => {
			if (doc.dr_type) types.add(doc.dr_type);
		});
		return Array.from(types).sort();
	}, [doctors]);

	const [isModalOpen, setIsModalOpen] = useState(false);
	const [tempSettings, setTempSettings] = useState<IVisibilitySettings>(settings);

	const handleOpenModal = () => {
		setTempSettings(settings);
		setIsModalOpen(true);
	};

	const handleSaveModal = () => {
		onChange(tempSettings);
		setIsModalOpen(false);
	};

	const handleCancelModal = () => {
		setTempSettings(settings);
		setIsModalOpen(false);
	};

	// Multi-select helper handlers for modal
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

		setTempSettings({ ...tempSettings, [key]: updated });
	};

	const formatDisplay = (
		key: keyof IVisibilitySettings,
		typeName: string,
		sourceSettings: IVisibilitySettings = settings,
	) => {
		const current = sourceSettings[key] || ["all"];
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

	return (
		<>
			<div className="bg-zinc-100/50 rounded-lg p-4 w-full text-zinc-950">
				<div className="flex items-center gap-2 text-blue-700 mb-2">
					<RiEyeLine className="size-5 text-blue-600 shrink-0" />
					<h3 className="font-bold text-sm text-zinc-950">Visibility Settings</h3>
				</div>
				<p className="text-xs text-zinc-600 font-medium mb-4">
					Limit access to your medical insights so only authorized doctors can view this knowledge.
				</p>

				<div className="flex flex-col gap-3">
					<div>
						<label className="text-xs text-zinc-700 font-semibold block mb-0.5">Clinic</label>
						<p className="text-sm font-semibold text-zinc-900">{formatDisplay("clinics", "Clinic")}</p>
					</div>
					<div>
						<label className="text-xs text-zinc-700 font-semibold block mb-0.5">Doctor Type</label>
						<p className="text-sm font-semibold text-zinc-900">{formatDisplay("doctor_types", "Doctor Type")}</p>
					</div>
					<div>
						<label className="text-xs text-zinc-700 font-semibold block mb-0.5">Doctor</label>
						<p className="text-sm font-semibold text-zinc-900">{formatDisplay("doctors", "Doctor")}</p>
					</div>

					{isEditMode && (
						<Button
							type="button"
							variant="outline"
							className="w-fit mt-2 border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-100 font-semibold rounded-lg px-4 h-9 text-sm transition-colors cursor-pointer shadow-none gap-2"
							onClick={handleOpenModal}
						>
							<RiEdit2Line className="size-4 text-zinc-700" />
							Edit Visibility
						</Button>
					)}
				</div>
			</div>

			<Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
				<DialogContent className="sm:max-w-md p-0 flex flex-col gap-0 rounded-lg overflow-hidden bg-white border border-gray-200 shadow-none">
					<DialogHeader className="p-4 border-b border-gray-100 flex flex-col gap-0.5">
						<DialogTitle className="text-base font-semibold text-foreground">
							Edit Visibility Settings
						</DialogTitle>
						<DialogDescription className="text-xs text-muted-foreground">
							Configure access limits for this knowledge document.
						</DialogDescription>
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
										displayText={formatDisplay("clinics", "Clinic", tempSettings)}
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
										displayText={formatDisplay("doctor_types", "Doctor Type", tempSettings)}
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
										displayText={formatDisplay("doctors", "Doctor", tempSettings)}
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
							onClick={handleCancelModal}
						>
							Cancel
						</Button>
						<Button
							type="button"
							className="bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg px-4 h-10 gap-1.5 shadow-none transition-colors cursor-pointer disabled:opacity-50"
							disabled={
								(tempSettings.clinics && tempSettings.clinics.length === 0) ||
								(tempSettings.doctor_types && tempSettings.doctor_types.length === 0) ||
								(tempSettings.doctors && tempSettings.doctors.length === 0)
							}
							onClick={handleSaveModal}
						>
							<RiCheckLine className="size-4" />
							Save Changes
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</>
	);
}
