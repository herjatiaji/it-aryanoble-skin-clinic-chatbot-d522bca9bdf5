"use client";

import { useDebounce } from "@/hooks/use-debounce";
import { usePagination } from "@/hooks/use-pagination";
import { useTableSort } from "@/hooks/use-table-sort";
import { useMemo, useState } from "react";
import { useBranches } from "../../branches/hooks/use-branches";
import type { UserResponse } from "../api/types";
import { useUsers } from "./use-users";

export function useUsersState() {
	const [activeTab, setActiveTab] = useState<string>("staff");
	const [searchQuery, setSearchQuery] = useState("");
	const debouncedSearch = useDebounce(searchQuery, 300);
	const [selectedDrType, setSelectedDrType] = useState<string>("all");
	const [selectedBranches, setSelectedBranches] = useState<string[]>([]);
	const [isBranchPopoverOpen, setIsBranchPopoverOpen] = useState(false);
	const [branchSearchQuery, setBranchSearchQuery] = useState("");
	const debouncedBranchSearch = useDebounce(branchSearchQuery, 200);

	const { data: staffData = [], isLoading: isStaffLoading } = useUsers("STAFF");
	const { data: doctorData = [], isLoading: isDoctorLoading } = useUsers("DOCTOR");
	const { data: branches = [] } = useBranches();

	const staffSort = useTableSort();
	const doctorSort = useTableSort();

	const [selectedDoctor, setSelectedDoctor] = useState<UserResponse | null>(null);
	const [isSheetOpen, setIsSheetOpen] = useState(false);

	const [isAddUserOpen, setIsAddUserOpen] = useState(false);
	const [selectedStaff, setSelectedStaff] = useState<UserResponse | null>(null);
	const [isViewStaffOpen, setIsViewStaffOpen] = useState(false);

	const handleViewDoctor = (doctor: UserResponse) => {
		setSelectedDoctor(doctor);
		setIsSheetOpen(true);
	};

	const handleViewStaff = (staff: UserResponse) => {
		setSelectedStaff(staff);
		setIsViewStaffOpen(true);
	};

	const selectedDoctorLive = doctorData.find((d) => d.id === selectedDoctor?.id) || selectedDoctor;
	const selectedStaffLive = staffData.find((s) => s.id === selectedStaff?.id) || selectedStaff;

	// Extract unique doctor types
	const doctorTypes = useMemo(() => {
		const types = new Set<string>();
		doctorData.forEach((d) => {
			if (d.dr_type) types.add(d.dr_type);
		});
		return Array.from(types).sort();
	}, [doctorData]);

	// Filtered items based on search query
	const filteredStaff = useMemo(() => {
		let result = staffData;
		if (debouncedSearch.trim()) {
			const q = debouncedSearch.toLowerCase();
			result = staffData.filter(
				(s) =>
					s.name?.toLowerCase().includes(q) ||
					s.email?.toLowerCase().includes(q) ||
					s.roles?.some((r) => r.name.toLowerCase().includes(q)),
			);
		}
		return staffSort.sortItems<UserResponse>(result);
	}, [staffData, debouncedSearch, staffSort]);

	const isAllBranchesSelected = branches.length > 0 && selectedBranches.length === branches.length;

	const filteredDoctors = useMemo(() => {
		const result = doctorData.filter((d) => {
			// Search query match
			if (debouncedSearch.trim()) {
				const q = debouncedSearch.toLowerCase();
				const matchesQuery =
					d.name?.toLowerCase().includes(q) ||
					d.email?.toLowerCase().includes(q) ||
					d.employee_id?.toLowerCase().includes(q) ||
					d.dr_type?.toLowerCase().includes(q) ||
					d.branches?.some((b) => b.name.toLowerCase().includes(q));
				if (!matchesQuery) return false;
			}

			// Doctor Type filter
			if (selectedDrType !== "all") {
				if (d.dr_type !== selectedDrType) return false;
			}

			// Multi-Branch filter
			if (selectedBranches.length > 0 && selectedBranches.length < branches.length) {
				const hasBranch = d.branches?.some(
					(b) => selectedBranches.includes(b.id) || selectedBranches.includes(b.name),
				);
				if (!hasBranch) return false;
			}

			return true;
		});

		return doctorSort.sortItems<UserResponse>(result);
	}, [doctorData, debouncedSearch, selectedDrType, selectedBranches, branches.length, doctorSort]);

	const staffPagination = usePagination({ items: filteredStaff, initialPageSize: 10 });
	const doctorPagination = usePagination({ items: filteredDoctors, initialPageSize: 10 });

	const handleToggleBranch = (id: string) => {
		setSelectedBranches((prev) =>
			prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
		);
	};

	const handleToggleAllBranches = () => {
		if (isAllBranchesSelected) {
			setSelectedBranches([]);
		} else {
			setSelectedBranches(branches.map((b) => b.id));
		}
	};

	const handleResetBranches = () => {
		setSelectedBranches([]);
	};

	const filteredBranchOptions = useMemo(() => {
		const q = debouncedBranchSearch.toLowerCase().trim();
		if (!q) return branches;
		return branches.filter((b) => b.name.toLowerCase().includes(q));
	}, [branches, debouncedBranchSearch]);

	// Selected filter labels
	const selectedBranchLabel = useMemo(() => {
		if (selectedBranches.length === 0 || isAllBranchesSelected) return "All branches";
		if (selectedBranches.length === 1) {
			const b = branches.find((item) => item.id === selectedBranches[0]);
			return b ? b.name : "1 branch selected";
		}
		return `${selectedBranches.length} branches selected`;
	}, [selectedBranches, branches, isAllBranchesSelected]);

	const selectedDrTypeName = useMemo(() => {
		if (selectedDrType === "all") return "Select doctor type";
		return selectedDrType;
	}, [selectedDrType]);

	const handleClearStaffFilter = () => {
		setSearchQuery("");
	};

	const handleClearDoctorFilter = () => {
		setSearchQuery("");
		setSelectedDrType("all");
		setSelectedBranches([]);
	};

	const hasStaffFilter = Boolean(searchQuery.trim());
	const hasDoctorFilter =
		Boolean(searchQuery.trim()) || selectedDrType !== "all" || selectedBranches.length > 0;

	return {
		activeTab,
		setActiveTab,
		searchQuery,
		setSearchQuery,
		selectedDrType,
		setSelectedDrType,
		doctorTypes,
		selectedDrTypeName,
		selectedBranches,
		selectedBranchLabel,
		isBranchPopoverOpen,
		setIsBranchPopoverOpen,
		branchSearchQuery,
		setBranchSearchQuery,
		filteredBranchOptions,
		isAllBranchesSelected,
		handleToggleBranch,
		handleToggleAllBranches,
		handleResetBranches,
		// Data & Loading
		staffData,
		isStaffLoading,
		doctorData,
		isDoctorLoading,
		// Filtered & Pagination
		filteredStaff,
		filteredDoctors,
		staffPagination,
		doctorPagination,
		// Modals & Selection
		selectedDoctorLive,
		isSheetOpen,
		setIsSheetOpen,
		handleViewDoctor,
		selectedStaffLive,
		isViewStaffOpen,
		setIsViewStaffOpen,
		handleViewStaff,
		isAddUserOpen,
		setIsAddUserOpen,
		// Filters clearing
		hasStaffFilter,
		hasDoctorFilter,
		handleClearStaffFilter,
		handleClearDoctorFilter,
		// Sorting
		staffSortKey: staffSort.sortKey,
		staffSortOrder: staffSort.sortOrder,
		handleStaffSort: staffSort.handleSort,
		doctorSortKey: doctorSort.sortKey,
		doctorSortOrder: doctorSort.sortOrder,
		handleDoctorSort: doctorSort.handleSort,
	};
}
