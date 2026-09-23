import React from "react";
import {
	RiAlertLine,
	RiHeartPulseLine,
	RiMedicineBottleLine,
	RiStethoscopeLine,
} from "@remixicon/react";
import type { DiagnosisCardData } from "../types";

export function DiagnosisCard({ data }: { data: DiagnosisCardData }) {
	const {
		primaryDiagnosis,
		severity,
		patientCondition,
		treatment,
		product,
		notes,
		contraindications,
	} = data;

	return (
		<div className="not-prose my-2.5 rounded-lg border border-zinc-200/80 bg-white p-3.5 flex flex-col gap-3 shadow-none">
			{/* Card Title Header */}
			<div className="flex items-center justify-between gap-2 border-b border-zinc-100 pb-2">
				<div className="flex items-center gap-2 min-w-0">
					<div className="size-6 rounded-md bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
						<RiHeartPulseLine className="size-3.5" />
					</div>
					<h4 className="text-sm font-semibold text-zinc-950 tracking-tight">
						Ringkasan Diagnosis Klinis
					</h4>
				</div>
				{severity && (
					<span className="text-xs font-medium bg-zinc-100 text-zinc-700 border border-zinc-200 px-2 py-0.5 rounded shrink-0">
						{severity}
					</span>
				)}
			</div>

			{/* Primary Diagnosis */}
			{primaryDiagnosis && (
				<div className="text-xs sm:text-sm leading-normal">
					<span className="font-semibold text-zinc-900">Diagnosis Utama:</span>{" "}
					<span className="text-zinc-950 font-medium">{primaryDiagnosis}</span>
				</div>
			)}

			{/* Patient Condition */}
			{patientCondition && (
				<div className="text-xs sm:text-sm text-zinc-800 leading-normal">
					<span className="font-semibold text-zinc-900">Kondisi Klinis:</span>{" "}
					<span>{patientCondition}</span>
				</div>
			)}

			{/* Recommendations Grid */}
			{(treatment || product) && (
				<div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
					{treatment && (
						<div className="p-2.5 rounded-md border border-zinc-200 bg-zinc-50/50 flex flex-col gap-1">
							<div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-900">
								<RiStethoscopeLine className="size-3.5 text-blue-600 shrink-0" />
								<span>Tindakan Klinis</span>
							</div>
							<p className="text-xs sm:text-sm text-zinc-800 m-0 leading-normal">{treatment}</p>
						</div>
					)}
					{product && (
						<div className="p-2.5 rounded-md border border-zinc-200 bg-zinc-50/50 flex flex-col gap-1">
							<div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-900">
								<RiMedicineBottleLine className="size-3.5 text-emerald-600 shrink-0" />
								<span>Homecare Skincare</span>
							</div>
							<p className="text-xs sm:text-sm text-zinc-800 m-0 leading-normal">{product}</p>
						</div>
					)}
				</div>
			)}

			{/* Clinical Notes */}
			{notes && notes.length > 0 && (
				<div className="text-xs sm:text-sm text-zinc-700 space-y-1">
					{notes.map((note, idx) => (
						<div key={idx} className="leading-normal">
							• {note}
						</div>
					))}
				</div>
			)}

			{/* Contraindications Warning */}
			{contraindications && contraindications.length > 0 && (
				<div className="p-2.5 rounded-md border-l-2 border-red-600 bg-red-50/50 text-xs sm:text-sm">
					<div className="flex items-center gap-1.5 font-semibold text-red-950 mb-1 text-xs">
						<RiAlertLine className="size-3.5 text-red-600 shrink-0" />
						<span>Kontraindikasi & Perhatian</span>
					</div>
					<div className="space-y-0.5 pl-4">
						{contraindications.map((item, idx) => (
							<div key={idx} className="text-red-950 leading-normal">
								• {item}
							</div>
						))}
					</div>
				</div>
			)}
		</div>
	);
}
