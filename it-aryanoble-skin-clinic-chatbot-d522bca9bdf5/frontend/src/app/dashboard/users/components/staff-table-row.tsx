"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { RiEyeLine } from "@remixicon/react";
import type { UserResponse } from "../api/types";

interface StaffTableRowProps {
	staff: UserResponse;
	onView: (staff: UserResponse) => void;
}

export function StaffTableRow({ staff, onView }: StaffTableRowProps) {
	const initials = staff.name
		? staff.name
				.split(" ")
				.map((n: string) => n[0])
				.slice(0, 2)
				.join("")
		: "S";

	const roleName = staff.roles && staff.roles.length > 0 ? staff.roles[0].name : "Staff";

	return (
		<TableRow>
			<TableCell>
				<div className="flex items-center gap-3">
					<Avatar className="h-10 w-10">
						<AvatarFallback className="bg-gray-100 text-gray-600 font-medium">
							{initials}
						</AvatarFallback>
					</Avatar>
					<div className="flex flex-col">
						<span className="font-medium text-sm text-gray-900">{staff.name}</span>
					</div>
				</div>
			</TableCell>
			<TableCell>
				<Badge
					variant="secondary"
					className="bg-blue-50 text-blue-700 border-blue-200 font-medium text-xs uppercase"
				>
					{roleName}
				</Badge>
			</TableCell>
			<TableCell className="text-gray-900">{staff.email}</TableCell>
			<TableCell className="text-right">
				<div className="flex justify-end gap-2">
					<Button
						variant="outline"
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-3 h-8 font-medium text-xs transition-colors cursor-pointer shadow-none gap-1.5"
						onClick={() => onView(staff)}
					>
						<RiEyeLine className="size-3.5 shrink-0" />
						View
					</Button>
				</div>
			</TableCell>
		</TableRow>
	);
}
