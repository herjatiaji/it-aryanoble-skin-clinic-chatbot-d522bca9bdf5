"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { RiCheckLine, RiAlertLine, RiLoader4Line, RiPlayLine, RiArrowDownSLine, RiArrowUpSLine } from "@remixicon/react";
import type { IngestQualityReport } from "../../api/types";
import { useRunQualityCheck } from "../../hooks/use-knowledge";

const STRUCTURE_LABELS: Record<string, string> = {
	placeholder_value: "Nilai kosong ('null')",
	table_column_mismatch: "Tabel dengan jumlah kolom tidak konsisten",
	heading_only: "Potongan berisi judul saja",
	empty: "Potongan kosong",
	oversized: "Potongan terlalu panjang",
	duplicate: "Potongan duplikat",
};

const GRADE_LABELS: Record<string, string> = {
	partial: "Sebagian",
	wrong: "Salah",
	missing: "Tidak terjawab",
};

function pct(v: number | null | undefined) {
	return v === null || v === undefined ? "-" : `${Math.round(v * 100)}%`;
}

/** What the ingest quality check measured for this document: its own text reaching the chatbot, structure, test questions. */
export function IngestQualityCard({ knowledgeId, report }: { knowledgeId: string; report?: IngestQualityReport }) {
	const runCheck = useRunQualityCheck(knowledgeId);
	const [showDetails, setShowDetails] = useState(false);

	const pass = report?.status === "PASS";
	const structure = Object.entries(report?.structure || {});
	const probes = report?.probes;

	return (
		<div className="border border-zinc-200 rounded-xl p-4 bg-white shadow-xs flex flex-col gap-3">
			<div className="flex items-center justify-between gap-3 pb-2 border-b border-zinc-100">
				<div className="flex items-center gap-2">
					{report ? (
						pass ? (
							<RiCheckLine className="size-4 text-emerald-600" />
						) : (
							<RiAlertLine className="size-4 text-amber-500" />
						)
					) : null}
					<h4 className="text-xs font-bold text-zinc-900 uppercase tracking-wider">Kualitas Ingest</h4>
					{report && (
						<span
							className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
								pass
									? "text-emerald-700 bg-emerald-50 border-emerald-200"
									: "text-amber-800 bg-amber-50 border-amber-200"
							}`}
						>
							{pass ? "LULUS" : "PERLU DITINJAU"}
						</span>
					)}
				</div>
				<Button
					variant="outline"
					size="sm"
					disabled={runCheck.isPending}
					onClick={() => runCheck.mutate()}
					className="h-8 text-xs font-medium bg-white hover:bg-zinc-50 border-zinc-200 text-zinc-700 rounded-lg shadow-none"
				>
					{runCheck.isPending ? (
						<RiLoader4Line className="size-3.5 mr-1 animate-spin" />
					) : (
						<RiPlayLine className="size-3.5 mr-1" />
					)}
					Periksa Ulang
				</Button>
			</div>

			{!report ? (
				<p className="text-xs text-zinc-500">
					Dokumen ini belum diperiksa. Pemeriksaan berjalan otomatis setelah ingest dan publish, atau tekan
					Periksa Ulang.
				</p>
			) : (
				<>
					<div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-center">
						<div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
							<div className="text-lg font-bold text-zinc-800">{pct(report.coverage)}</div>
							<div className="text-[10px] uppercase font-semibold text-zinc-500 mt-0.5">
								Teks dokumen masuk ke chatbot
							</div>
						</div>
						<div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
							<div className="text-lg font-bold text-zinc-800">
								{probes?.total ? `${probes.correct}/${probes.total}` : "-"}
							</div>
							<div className="text-[10px] uppercase font-semibold text-zinc-500 mt-0.5">
								Pertanyaan uji dijawab benar
							</div>
						</div>
						<div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
							<div className="text-lg font-bold text-zinc-800">{structure.length}</div>
							<div className="text-[10px] uppercase font-semibold text-zinc-500 mt-0.5">Jenis cacat struktur</div>
						</div>
					</div>

					{report.coverage === null && (
						<p className="text-[11px] text-zinc-500">
							File ini tidak punya teks sendiri (hasil scan atau gambar), jadi cakupan teks tidak dapat diukur;
							pertanyaan uji dibuat dari konten yang dipublikasikan.
						</p>
					)}
					{probes?.error && <p className="text-[11px] text-red-600">Pertanyaan uji gagal dijalankan: {probes.error}</p>}

					<button
						type="button"
						onClick={() => setShowDetails((v) => !v)}
						className="flex items-center gap-1 text-[11px] font-medium text-blue-700 hover:underline self-start cursor-pointer"
					>
						{showDetails ? <RiArrowUpSLine className="size-3.5" /> : <RiArrowDownSLine className="size-3.5" />}
						{showDetails ? "Sembunyikan rincian" : "Lihat rincian"}
					</button>

					{showDetails && (
						<div className="flex flex-col gap-3 text-xs text-zinc-700">
							{(report.missing_examples || []).length > 0 && (
								<div>
									<div className="font-semibold mb-1">Contoh teks dokumen yang tidak masuk ke chatbot</div>
									<ul className="list-disc pl-5 space-y-0.5">
										{report.missing_examples!.map((line, i) => (
											<li key={i}>{line}</li>
										))}
									</ul>
								</div>
							)}
							{structure.length > 0 && (
								<div>
									<div className="font-semibold mb-1">Cacat struktur</div>
									<ul className="list-disc pl-5 space-y-0.5">
										{structure.map(([key, v]) => (
											<li key={key}>
												{STRUCTURE_LABELS[key] || key}: {v.count}
											</li>
										))}
									</ul>
								</div>
							)}
							{(probes?.failures || []).length > 0 && (
								<div>
									<div className="font-semibold mb-1">Pertanyaan uji yang belum terjawab benar</div>
									<div className="flex flex-col gap-2">
										{probes!.failures!.map((f, i) => (
											<div key={i} className="rounded-lg border border-zinc-200 p-2.5 bg-zinc-50/60">
												<div className="font-medium text-zinc-900">{f.question}</div>
												<div className="mt-1">
													<span className="text-zinc-500">Di dokumen: </span>
													{f.answer_quote}
												</div>
												<div className="mt-1">
													<span className="text-zinc-500">Jawaban chatbot: </span>
													{f.answer.length > 300 ? `${f.answer.slice(0, 300)}…` : f.answer}
												</div>
												<div className="mt-1 text-[11px] text-amber-800">
													{GRADE_LABELS[f.grade] || f.grade}
													{f.retrieved ? "" : " · bagian dokumen ini tidak ditemukan saat pencarian"}
												</div>
											</div>
										))}
									</div>
								</div>
							)}
							{report.checked_at && (
								<div className="text-[11px] text-zinc-400">Diperiksa: {report.checked_at}</div>
							)}
						</div>
					)}
				</>
			)}
		</div>
	);
}
