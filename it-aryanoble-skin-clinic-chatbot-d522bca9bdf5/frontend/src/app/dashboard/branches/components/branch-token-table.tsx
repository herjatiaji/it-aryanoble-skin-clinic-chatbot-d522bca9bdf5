"use client";

import { SearchBar } from "@/components/shared/search-bar";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { useBranches } from "../hooks/use-branches";
import { ViewBranchSheet } from "./view-branch-sheet";

export function BranchTokenTable() {
	const { data: branches, isLoading } = useBranches();

	return (
		<div className="flex flex-col gap-4 w-full">
			<div className="flex items-center justify-between gap-4">
				{/* Search */}
				<SearchBar
					containerClassName="max-w-md flex-1"
					iconClassName="left-3 top-1/2 -translate-y-1/2 size-4 text-black-200"
					placeholder="Search for branch..."
					className="pl-9 border-black-50 text-sm h-10 rounded-lg"
				/>

				{/* Actions */}
				<div className="flex items-center gap-3">
					{/* Add Branch functionality has been moved to CIS Dashboard sync */}
				</div>
			</div>

			<div className="border border-black-50 rounded-md bg-white overflow-hidden">
				<Table>
					<TableHeader>
						<TableRow className="hover:bg-transparent border-b-black-50">
							<TableHead className="w-[30%]">Branch</TableHead>
							<TableHead>Tokens/Month</TableHead>
							<TableHead>Used</TableHead>
							<TableHead>Remaining</TableHead>
							<TableHead className="text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{isLoading ? (
							<TableRow>
								<TableCell colSpan={5} className="text-center py-8 text-gray-500">
									Loading branches...
								</TableCell>
							</TableRow>
						) : branches?.length === 0 ? (
							<TableRow>
								<TableCell colSpan={5} className="text-center py-8 text-gray-500">
									No branches found.
								</TableCell>
							</TableRow>
						) : (
							branches?.map((branch) => (
								<TableRow key={branch.id} className="border-b-black-50">
									<TableCell className="max-w-50">
										<div className="flex items-center gap-3">

											<div className="flex flex-col justify-center overflow-hidden">
												<span className="font-medium text-black-500 truncate">{branch.name}</span>
											</div>
										</div>
									</TableCell>
									<TableCell className="text-blue-600 font-medium">{branch.tokensMonth}</TableCell>
									<TableCell className="text-blue-600 font-medium">{branch.used}</TableCell>
									<TableCell className="text-blue-600 font-medium">{branch.remaining}</TableCell>
									<TableCell className="text-right">
										<div className="flex justify-end">
											<ViewBranchSheet branch={branch} />
										</div>
									</TableCell>
								</TableRow>
							))
						)}
					</TableBody>
				</Table>
			</div>
		</div>
	);
}
