"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { RiEdit2Line } from "@remixicon/react";
import { RoleDetailResponse } from "../api/types";

interface RolesTableRowProps {
	role: RoleDetailResponse;
	onEdit: (role: RoleDetailResponse) => void;
}

export function RolesTableRow({ role, onEdit }: RolesTableRowProps) {
	const isSystemAdmin = role.name.toUpperCase() === "ADMIN";
	const displayedAccesses = role.accesses?.slice(0, 4) ?? [];
	const remainingCount = (role.accesses?.length ?? 0) - 4;

	return (
		<TableRow>
			<TableCell>
				<div className="flex items-center gap-2">
					<span className="font-medium text-sm text-gray-900">{role.name}</span>
					{isSystemAdmin && (
						<Badge
							variant="secondary"
							className="bg-purple-50 text-purple-700 border-purple-200 text-[10px] font-semibold"
						>
							System
						</Badge>
					)}
				</div>
			</TableCell>
			<TableCell>
				<div className="flex flex-wrap gap-1.5 max-w-xl">
					{displayedAccesses.length > 0 ? (
						displayedAccesses.map((acc) => (
							<Badge
								key={acc}
								variant="secondary"
								className="bg-gray-100 text-gray-700 text-xs px-2 py-0.5 border border-gray-200"
							>
								{acc}
							</Badge>
						))
					) : (
						<span className="text-xs text-muted-foreground italic">No permissions assigned</span>
					)}
					{remainingCount > 0 && (
						<Badge
							variant="secondary"
							className="bg-blue-50 text-blue-700 border-blue-200 text-xs font-semibold"
						>
							+{remainingCount} more
						</Badge>
					)}
				</div>
			</TableCell>
			<TableCell className="text-right">
				<div className="flex justify-end gap-2">
					<Button
						variant="outline"
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-3 h-8 font-medium text-xs transition-colors cursor-pointer shadow-none gap-1.5"
						onClick={() => onEdit(role)}
					>
						<RiEdit2Line className="size-3.5 shrink-0" />
						Edit
					</Button>
				</div>
			</TableCell>
		</TableRow>
	);
}
