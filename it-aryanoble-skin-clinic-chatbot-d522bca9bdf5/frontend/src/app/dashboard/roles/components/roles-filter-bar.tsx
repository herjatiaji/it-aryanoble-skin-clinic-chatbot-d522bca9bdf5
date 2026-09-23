"use client";

import { SearchBar } from "@/components/shared/search-bar";
import { Button } from "@/components/ui/button";
import { RiAddLine } from "@remixicon/react";

interface RolesFilterBarProps {
	searchQuery: string;
	onSearchChange: (value: string) => void;
	onAddRole: () => void;
}

export function RolesFilterBar({ searchQuery, onSearchChange, onAddRole }: RolesFilterBarProps) {
	return (
		<div className="flex items-center justify-between mb-4">
			<SearchBar
				containerClassName="max-w-md"
				placeholder="Search for roles or permissions..."
				value={searchQuery}
				onChange={(e) => onSearchChange(e.target.value)}
			/>
			<Button
				className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg h-10 px-4 font-medium text-sm transition-colors cursor-pointer shadow-none gap-2"
				onClick={onAddRole}
			>
				<RiAddLine className="size-4 shrink-0" />
				Add New Role
			</Button>
		</div>
	);
}
