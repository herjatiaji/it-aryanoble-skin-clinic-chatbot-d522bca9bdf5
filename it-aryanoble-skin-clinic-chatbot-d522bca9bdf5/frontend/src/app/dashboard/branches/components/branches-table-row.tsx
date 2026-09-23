"use client";

import { TableCell, TableRow } from "@/components/ui/table";
import { BranchResponse } from "../api/types";
import { ViewBranchSheet } from "./view-branch-sheet";

interface BranchesTableRowProps {
	branch: BranchResponse;
	isGlobalLimitActive: boolean;
	globalBranchLimit: string;
}

export function BranchesTableRow({
	branch,
	isGlobalLimitActive,
	globalBranchLimit,
}: BranchesTableRowProps) {
	const hasCustomLimit = branch.has_custom_limit ?? false;
	const limit = hasCustomLimit
		? (branch.token_limit ?? 0)
		: isGlobalLimitActive
		? Number(globalBranchLimit)
		: (branch.token_limit ?? branch.tokensMonth ?? 0);
	const used = branch.used ?? 0;
	const remaining = Math.max(0, limit - used);

	return (
		<TableRow className="border-b-black-50">
			<TableCell className="font-medium text-black-500">{branch.code || "-"}</TableCell>
			<TableCell className="text-zinc-600">{branch.ecosystem || "-"}</TableCell>
			<TableCell className="font-medium text-black-500">{branch.name}</TableCell>
			<TableCell className="text-blue-600 font-medium">{limit.toLocaleString()}</TableCell>
			<TableCell className="text-blue-600 font-medium">{used.toLocaleString()}</TableCell>
			<TableCell className="text-blue-600 font-medium">{remaining.toLocaleString()}</TableCell>
			<TableCell className="text-right">
				<div className="flex justify-end">
					<ViewBranchSheet branch={branch} />
				</div>
			</TableCell>
		</TableRow>
	);
}
