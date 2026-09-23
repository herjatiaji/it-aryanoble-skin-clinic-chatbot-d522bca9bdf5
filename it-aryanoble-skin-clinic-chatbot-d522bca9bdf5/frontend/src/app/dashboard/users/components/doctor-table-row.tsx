"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { RiEyeLine } from "@remixicon/react";
import type { UserResponse } from "../api/types";

interface DoctorTableRowProps {
	doctor: UserResponse;
	onView: (doctor: UserResponse) => void;
}

export function DoctorTableRow({ doctor, onView }: DoctorTableRowProps) {
	const initials = doctor.name
		? doctor.name
				.replace("Dr. ", "")
				.split(" ")
				.map((n: string) => n[0])
				.slice(0, 2)
				.join("")
		: "D";

	const branchesLabel =
		doctor.branches && doctor.branches.length > 0
			? doctor.branches.map((b) => b.name).join(", ")
			: "No Branch";

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
						<span className="font-medium text-sm text-gray-900">{doctor.name}</span>
					</div>
				</div>
			</TableCell>
			<TableCell className="text-gray-900">{doctor.employee_id || "-"}</TableCell>
			<TableCell className="text-gray-900">{doctor.dr_type || "-"}</TableCell>
			<TableCell
				className="text-gray-900 text-sm truncate max-w-75"
				title={doctor.branches?.map((b) => b.name).join(", ")}
			>
				{branchesLabel}
			</TableCell>
			<TableCell className="text-gray-900">{doctor.ecosystem || "ERHA"}</TableCell>
			<TableCell className="text-gray-900">{doctor.email || "-"}</TableCell>
			<TableCell className="text-right">
				<div className="flex justify-end gap-2">
					<Button
						variant="outline"
						className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-3 h-8 font-medium text-xs transition-colors cursor-pointer shadow-none gap-1.5"
						onClick={() => onView(doctor)}
					>
						<RiEyeLine className="size-3.5 shrink-0" />
						View
					</Button>
				</div>
			</TableCell>
		</TableRow>
	);
}
