import React from "react";
import { RiFileList3Line, RiShieldCheckLine, RiSparklingLine } from "@remixicon/react";
import type { SOPCardData } from "../types";

export function ProcedureStepperCard({ data }: { data: SOPCardData }) {
	const { title, preCare, steps, aftercare } = data;

	return (
		<div className="not-prose my-2.5 rounded-lg border border-zinc-200/80 bg-white p-3.5 flex flex-col gap-3 shadow-none">
			{/* Header */}
			<div className="flex items-center gap-2 border-b border-zinc-100 pb-2">
				<div className="size-6 rounded-md bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
					<RiFileList3Line className="size-3.5" />
				</div>
				<h4 className="text-sm font-semibold text-zinc-950 tracking-tight">
					{title || "Protokol & Tahapan Tindakan Klinis"}
				</h4>
			</div>

			{/* Pre-Care Box */}
			{preCare && preCare.length > 0 && (
				<div className="p-2.5 rounded-md border border-blue-200/80 bg-blue-50/40 text-xs sm:text-sm">
					<div className="flex items-center gap-1.5 font-semibold text-blue-950 mb-1 text-xs">
						<RiShieldCheckLine className="size-3.5 text-blue-600 shrink-0" />
						<span>Persiapan Sebelum Tindakan (Pre-Care)</span>
					</div>
					<div className="space-y-1 pl-4">
						{preCare.map((item, idx) => (
							<div key={idx} className="text-zinc-800 leading-normal">
								• {item}
							</div>
						))}
					</div>
				</div>
			)}

			{/* Numbered Stepper Steps */}
			{steps && steps.length > 0 && (
				<div className="flex flex-col gap-0 relative pl-0.5 py-1">
					{steps.map((step, idx) => {
						const isLast = idx === steps.length - 1;
						const hasSubtext = Boolean(step.title && step.description);
						return (
							<div
								key={idx}
								className={`flex items-start gap-2.5 relative ${
									isLast ? "pb-0" : hasSubtext ? "pb-3.5" : "pb-3.5 sm:pb-4"
								}`}
							>
								{!isLast && (
									<div className="absolute left-2.75 top-6.5 bottom-0 w-px bg-zinc-200/80" />
								)}
								<div className="size-5.5 shrink-0 rounded-md bg-zinc-100 text-zinc-700 border border-zinc-200/80 font-semibold text-xs flex items-center justify-center z-10 mt-0.5">
									{step.stepNumber || idx + 1}
								</div>
								<div className="flex-1 min-w-0 pt-0.5">
									{step.title && (
										<h5 className="text-xs sm:text-sm font-semibold text-zinc-950 leading-snug">
											{step.title}
										</h5>
									)}
									{step.description && (
										<p
											className={`text-xs sm:text-sm text-zinc-700 leading-normal m-0 ${
												step.title ? "mt-0.5" : ""
											}`}
										>
											{step.description}
										</p>
									)}
								</div>
							</div>
						);
					})}
				</div>
			)}

			{/* Aftercare Box */}
			{aftercare && aftercare.length > 0 && (
				<div className="p-2.5 rounded-md border border-emerald-200/80 bg-emerald-50/40 text-xs sm:text-sm">
					<div className="flex items-center gap-1.5 font-semibold text-emerald-950 mb-1 text-xs">
						<RiSparklingLine className="size-3.5 text-emerald-600 shrink-0" />
						<span>Perawatan Pasca Tindakan (Aftercare)</span>
					</div>
					<div className="space-y-1 pl-4">
						{aftercare.map((item, idx) => (
							<div key={idx} className="text-zinc-800 leading-normal">
								• {item}
							</div>
						))}
					</div>
				</div>
			)}
		</div>
	);
}
