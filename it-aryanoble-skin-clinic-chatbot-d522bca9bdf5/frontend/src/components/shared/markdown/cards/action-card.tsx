import React from "react";
import {
	RiArrowRightLine,
	RiDeleteBin7Line,
	RiFileEditLine,
	RiFileTextLine,
	RiInputField,
} from "@remixicon/react";
import type { ActionConfirmationData } from "../types";

export function ActionConfirmationCard({ data }: { data: ActionConfirmationData }) {
	const {
		actionType,
		knowledgeId,
		fieldName,
		newValue,
		summary,
		confirmationPrompt,
	} = data;
	const isDelete = actionType === "delete_preview";

	return (
		<div className="not-prose my-2.5 rounded-lg border border-zinc-200 bg-white p-3.5 flex flex-col gap-2.5 shadow-none">
			{/* Header */}
			<div className="flex items-center justify-between gap-2 border-b border-zinc-100 pb-2.5">
				<div className="flex items-center gap-2 min-w-0">
					<div
						className={`size-6 rounded-md flex items-center justify-center shrink-0 ${
							isDelete ? "bg-red-50 text-red-600" : "bg-blue-50 text-blue-600"
						}`}
					>
						{isDelete ? (
							<RiDeleteBin7Line className="size-3.5" />
						) : (
							<RiFileEditLine className="size-3.5" />
						)}
					</div>
					<h4 className="text-xs sm:text-sm font-semibold text-zinc-950 tracking-tight">
						{isDelete ? "Confirm Document Deletion" : "Preview Knowledge Changes"}
					</h4>
				</div>
				<span
					className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
						isDelete
							? "bg-red-50 text-red-700 border-red-200"
							: "bg-blue-50 text-blue-700 border-blue-200"
					}`}
				>
					{isDelete ? "Deletion" : "Update"}
				</span>
			</div>

			{/* Details Box */}
			<div className="rounded-lg border border-zinc-200/80 bg-zinc-50/70 p-3 text-xs sm:text-sm text-zinc-800 space-y-2 shadow-none">
				{knowledgeId && (
					<div className="flex items-center gap-2 flex-wrap">
						<div className="flex items-center gap-1 text-zinc-500 font-medium">
							<RiFileTextLine className="size-3.5 text-zinc-400" />
							<span>Knowledge ID:</span>
						</div>
						<span className="font-mono text-xs bg-white px-2 py-0.5 rounded-md border border-zinc-200 text-zinc-900">
							{knowledgeId}
						</span>
					</div>
				)}
				{fieldName && (
					<div className="flex items-center gap-2 flex-wrap">
						<div className="flex items-center gap-1 text-zinc-500 font-medium">
							<RiInputField className="size-3.5 text-zinc-400" />
							<span>Target Field:</span>
						</div>
						<span className="font-semibold text-zinc-950">{fieldName}</span>
					</div>
				)}
				{newValue && (
					<div className="flex items-center gap-2 flex-wrap">
						<div className="flex items-center gap-1 text-zinc-500 font-medium">
							<RiArrowRightLine className="size-3.5 text-blue-500" />
							<span>New Value:</span>
						</div>
						<span className="font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-200">
							{newValue}
						</span>
					</div>
				)}
				{summary && <p className="m-0 text-zinc-700 leading-normal pt-0.5">{summary}</p>}
			</div>

			{confirmationPrompt && (
				<p className="text-xs text-zinc-500 italic m-0">
					{confirmationPrompt}
				</p>
			)}
		</div>
	);
}
