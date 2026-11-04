"use client";

import React, { useState } from "react";
import {
	useQualityGate,
	useUpdateEvidence,
	useResolveEvidence,
	useRegenerateSummary,
} from "../../hooks/use-knowledge";
import { EvidenceItem, AssetItem } from "../../api/types";
import { IngestQualityCard } from "./ingest-quality-card";
import { Button } from "@/components/ui/button";
import {
	RiShieldCheckLine,
	RiAlertLine,
	RiCheckLine,
	RiEdit2Line,
	RiRefreshLine,
	RiImage2Line,
	RiFileTextLine,
	RiFileList3Line,
	RiCloseLine,
	RiLoader4Line,
	RiExternalLinkLine,
	RiInformationLine,
} from "@remixicon/react";

interface QualityGatePanelProps {
	knowledgeId: string;
	isEditMode?: boolean;
	onSummaryRegenerated?: (newSummary: string) => void;
}

export function QualityGatePanel({
	knowledgeId,
	isEditMode = false,
	onSummaryRegenerated,
}: QualityGatePanelProps) {
	const { data: qgData, isLoading, refetch } = useQualityGate(knowledgeId);
	const updateEvidenceMutation = useUpdateEvidence(knowledgeId);
	const resolveEvidenceMutation = useResolveEvidence(knowledgeId);
	const regenerateSummaryMutation = useRegenerateSummary(knowledgeId);

	const [editingEvidence, setEditingEvidence] = useState<EvidenceItem | null>(null);
	const [editTitle, setEditTitle] = useState("");
	const [editBody, setEditBody] = useState("");
	const [editAttributesStr, setEditAttributesStr] = useState("");
	const [activeFilter, setActiveFilter] = useState<"ALL" | "REVIEW" | "VISUAL">("ALL");

	if (isLoading) {
		return (
			<div className="flex flex-col items-center justify-center p-12 text-zinc-500 gap-3">
				<RiLoader4Line className="size-6 animate-spin text-blue-600" />
				<span className="text-xs font-medium">Memuat audit Quality Gate & Readiness...</span>
			</div>
		);
	}

	if (!qgData) {
		return (
			<div className="p-6 text-center text-zinc-500 text-xs">
				Data audit Quality Gate belum tersedia untuk dokumen ini.
			</div>
		);
	}

	const readiness = qgData.readiness;
	const parseReport = qgData.parse_report || {};
	const disposition = parseReport.disposition_summary || {
		evidence_count: qgData.total_evidence_count || 0,
		context_rows: 0,
		excluded_rows: 0,
	};
	const totalRows = (disposition.evidence_count || 0) + (disposition.context_rows || 0) + (disposition.excluded_rows || 0);
	const evidencePercent = totalRows > 0 ? Math.round((disposition.evidence_count / totalRows) * 100) : 100;

	const visualSummary = qgData.visual_summary || {
		total: 0,
		completed: 0,
		review_required: 0,
		failed: 0,
	};

	const filteredEvidences = (qgData.evidences || []).filter((ev) => {
		if (activeFilter === "REVIEW") {
			return ["REVIEW_REQUIRED", "LOW_CONFIDENCE", "PARTIAL", "VISION_FAILED"].includes(
				ev.visual_analysis_status || ""
			);
		}
		if (activeFilter === "VISUAL") {
			return ev.evidence_type === "VISUAL" || ev.visual_analysis_status !== null;
		}
		return true;
	});

	const handleOpenEdit = (ev: EvidenceItem) => {
		setEditingEvidence(ev);
		setEditTitle(ev.title || "");
		setEditBody(ev.body || "");
		setEditAttributesStr(JSON.stringify(ev.attributes || {}, null, 2));
	};

	const handleSaveEvidence = async () => {
		if (!editingEvidence) return;
		let parsedAttrs = editingEvidence.attributes;
		try {
			if (editAttributesStr.trim()) {
				parsedAttrs = JSON.parse(editAttributesStr);
			}
		} catch {
			alert("Format JSON Attributes tidak valid. Silakan periksa kembali.");
			return;
		}

		await updateEvidenceMutation.mutateAsync({
			evidenceId: editingEvidence.id,
			data: {
				title: editTitle.trim() || undefined,
				body: editBody.trim(),
				attributes: parsedAttrs,
			},
		});
		setEditingEvidence(null);
	};

	const handleResolve = async (evidenceId: string) => {
		await resolveEvidenceMutation.mutateAsync(evidenceId);
	};

	const handleRegenerateSummary = async () => {
		const res = await regenerateSummaryMutation.mutateAsync();
		if (res && res.summary_md && onSummaryRegenerated) {
			onSummaryRegenerated(res.summary_md);
		}
	};

	return (
		<div className="flex flex-col gap-6 p-4 max-w-5xl mx-auto w-full">
			{/* 1. Readiness Gate Banner (D9) */}
			<div
				className={`rounded-xl border p-4.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-colors ${
					readiness.is_ready
						? "bg-emerald-50/70 border-emerald-200 text-emerald-950"
						: "bg-amber-50/80 border-amber-200 text-amber-950"
				}`}
			>
				<div className="flex items-start gap-3">
					<div
						className={`size-9 rounded-lg flex items-center justify-center shrink-0 ${
							readiness.is_ready
								? "bg-emerald-600 text-white"
								: "bg-amber-500 text-white"
						}`}
					>
						{readiness.is_ready ? (
							<RiShieldCheckLine className="size-5" />
						) : (
							<RiAlertLine className="size-5" />
						)}
					</div>
					<div>
						<div className="flex items-center gap-2">
							<h3 className="text-sm font-semibold">
								{readiness.is_ready
									? "Knowledge Readiness Gate: APPROVED & READY"
									: "Knowledge Readiness Gate: BLOCKED BY UNRESOLVED ITEMS (D9)"}
							</h3>
							<span
								className={`text-[11px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
									readiness.is_ready
										? "bg-emerald-200/80 text-emerald-800"
										: "bg-amber-200 text-amber-900"
								}`}
							>
								{readiness.is_ready ? "READY" : `${readiness.unresolved_items} PENDING REVIEW`}
							</span>
						</div>
						<p className="text-xs mt-1 text-zinc-600 leading-relaxed">
							{readiness.is_ready
								? "Seluruh ekstraksi kanonik, validasi gambar, dan diagram visual telah diverifikasi. Dokumen aman dipublish ke ACTIVE KB."
								: readiness.reasons[0] ||
								  "Dokumen dilarang bertransisi ke ACTIVE sebelum seluruh item visual dan review required diselesaikan oleh Admin."}
						</p>
					</div>
				</div>

				<div className="flex items-center gap-2 shrink-0">
					<Button
						variant="outline"
						size="sm"
						onClick={() => refetch()}
						className="h-8 text-xs font-medium bg-white hover:bg-zinc-50 border-zinc-200 text-zinc-700 rounded-lg shadow-none"
					>
						<RiRefreshLine className="size-3.5 mr-1" />
						Refresh Audit
					</Button>
				</div>
			</div>

			<IngestQualityCard knowledgeId={knowledgeId} report={parseReport.quality} />

			{/* 2. Extraction Disposition & Multimodal Metrics Grid */}
			<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
				{/* Card A: Disposition Summary (Zero Silent Drops) */}
				<div className="border border-zinc-200 rounded-xl p-4 bg-white shadow-xs flex flex-col justify-between">
					<div>
						<div className="flex items-center justify-between pb-2 mb-3 border-b border-zinc-100">
							<div className="flex items-center gap-2">
								<RiFileList3Line className="size-4 text-blue-600" />
								<h4 className="text-xs font-bold text-zinc-900 uppercase tracking-wider">
									Zero Silent Drops (Disposition)
								</h4>
							</div>
							<span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
								{evidencePercent}% Preserved
							</span>
						</div>

						<div className="grid grid-cols-3 gap-2 text-center my-3">
							<div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-100">
								<div className="text-lg font-bold text-emerald-800">
									{disposition.evidence_count}
								</div>
								<div className="text-[10px] uppercase font-semibold text-emerald-600 mt-0.5">
									Evidence Rows
								</div>
							</div>
							<div className="p-2.5 rounded-lg bg-blue-50/60 border border-blue-100">
								<div className="text-lg font-bold text-blue-800">
									{disposition.context_rows}
								</div>
								<div className="text-[10px] uppercase font-semibold text-blue-600 mt-0.5">
									Context Headers
								</div>
							</div>
							<div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-200">
								<div className="text-lg font-bold text-zinc-600">
									{disposition.excluded_rows}
								</div>
								<div className="text-[10px] uppercase font-semibold text-zinc-500 mt-0.5">
									Excluded (Empty/Subtotal)
								</div>
							</div>
						</div>
					</div>

					<p className="text-[11px] text-zinc-500 leading-tight">
						Kontrak Ingestion memastikan 100% baris dokumen terdata tanpa pemotongan senyap.
					</p>
				</div>

				{/* Card B: Multimodal Asset Classification Summary */}
				<div className="border border-zinc-200 rounded-xl p-4 bg-white shadow-xs flex flex-col justify-between">
					<div>
						<div className="flex items-center justify-between pb-2 mb-3 border-b border-zinc-100">
							<div className="flex items-center gap-2">
								<RiImage2Line className="size-4 text-purple-600" />
								<h4 className="text-xs font-bold text-zinc-900 uppercase tracking-wider">
									Multimodal Visual Intelligence (D3)
								</h4>
							</div>
							<span className="text-[11px] font-medium text-zinc-500">
								{qgData.total_asset_count} Media Assets
							</span>
						</div>

						<div className="grid grid-cols-4 gap-1.5 text-center my-3">
							<div className="p-2 rounded-lg bg-purple-50/60 border border-purple-100">
								<div className="text-base font-bold text-purple-800">
									{visualSummary.total || qgData.total_asset_count}
								</div>
								<div className="text-[9px] uppercase font-semibold text-purple-600">
									Detected
								</div>
							</div>
							<div className="p-2 rounded-lg bg-emerald-50/60 border border-emerald-100">
								<div className="text-base font-bold text-emerald-800">
									{visualSummary.completed}
								</div>
								<div className="text-[9px] uppercase font-semibold text-emerald-600">
									Vision Done
								</div>
							</div>
							<div
								className={`p-2 rounded-lg border ${
									visualSummary.review_required > 0
										? "bg-amber-50 border-amber-200"
										: "bg-zinc-50 border-zinc-200"
								}`}
							>
								<div
									className={`text-base font-bold ${
										visualSummary.review_required > 0 ? "text-amber-700" : "text-zinc-600"
									}`}
								>
									{visualSummary.review_required}
								</div>
								<div
									className={`text-[9px] uppercase font-semibold ${
										visualSummary.review_required > 0 ? "text-amber-700" : "text-zinc-500"
									}`}
								>
									Review Req.
								</div>
							</div>
							<div className="p-2 rounded-lg bg-zinc-50 border border-zinc-200">
								<div className="text-base font-bold text-zinc-600">
									{visualSummary.failed || 0}
								</div>
								<div className="text-[9px] uppercase font-semibold text-zinc-500">
									Failed
								</div>
							</div>
						</div>
					</div>

					<p className="text-[11px] text-zinc-500 leading-tight">
						Dual-Output: VISUAL Evidence (teks penalaran semantik) + Visual Asset (display asli chat).
					</p>
				</div>
			</div>

			{/* 3. D1-a Evidence SSOT Action Banner: Regenerate Summary */}
			<div className="bg-gradient-to-r from-blue-50/90 to-indigo-50/80 border border-blue-200/80 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
				<div className="flex items-start gap-3">
					<div className="size-8 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0 mt-0.5">
						<RiRefreshLine className="size-4.5" />
					</div>
					<div>
						<div className="flex items-center gap-2">
							<span className="text-xs font-bold text-blue-900 uppercase tracking-wide">
								Keputusan D1-a: Evidence adalah SSOT
							</span>
							<span className="text-[10px] font-semibold bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
								Display Derivative
							</span>
						</div>
						<p className="text-xs text-blue-800/90 mt-0.5 leading-relaxed">
							Koreksi fakta klinis dilakukan langsung pada unit Evidence di bawah. Klik tombol untuk
							meregenerasi teks ringkasan secara bersih & sinkron tanpa mengubah relasi chunk.
						</p>
					</div>
				</div>

				<Button
					onClick={handleRegenerateSummary}
					disabled={regenerateSummaryMutation.isPending}
					className="h-9 px-4 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-none shrink-0 gap-1.5 cursor-pointer"
				>
					{regenerateSummaryMutation.isPending ? (
						<>
							<RiLoader4Line className="size-4 animate-spin" />
							Regenerating...
						</>
					) : (
						<>
							<RiRefreshLine className="size-4" />
							Regenerate Summary from Evidence
						</>
					)}
				</Button>
			</div>

			{/* 4. Evidence Inspection & Direct Correction Table (D1-a) */}
			<div className="border border-zinc-200 rounded-xl bg-white overflow-hidden shadow-xs">
				<div className="p-4 border-b border-zinc-200 flex flex-wrap items-center justify-between gap-3 bg-zinc-50/60">
					<div className="flex items-center gap-2">
						<RiFileTextLine className="size-4.5 text-zinc-700" />
						<h3 className="text-xs font-bold text-zinc-900 uppercase tracking-wider">
							Canonical Evidence Units ({filteredEvidences.length} items)
						</h3>
					</div>

					<div className="flex items-center gap-1.5">
						<button
							onClick={() => setActiveFilter("ALL")}
							className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
								activeFilter === "ALL"
									? "bg-zinc-800 text-white"
									: "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
							}`}
						>
							Semua ({qgData.evidences?.length || 0})
						</button>
						<button
							onClick={() => setActiveFilter("REVIEW")}
							className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
								activeFilter === "REVIEW"
									? "bg-amber-600 text-white"
									: "bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100"
							}`}
						>
							Review Required ({visualSummary.review_required})
						</button>
						<button
							onClick={() => setActiveFilter("VISUAL")}
							className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
								activeFilter === "VISUAL"
									? "bg-purple-600 text-white"
									: "bg-purple-50 text-purple-800 border border-purple-200 hover:bg-purple-100"
							}`}
						>
							Visual / Chart
						</button>
					</div>
				</div>

				<div className="divide-y divide-zinc-100 max-h-120 overflow-y-auto">
					{filteredEvidences.length === 0 ? (
						<div className="p-8 text-center text-zinc-400 text-xs">
							Tidak ada evidence yang sesuai dengan filter yang dipilih.
						</div>
					) : (
						filteredEvidences.map((ev) => {
							const needsReview = [
								"REVIEW_REQUIRED",
								"LOW_CONFIDENCE",
								"PARTIAL",
								"VISION_FAILED",
							].includes(ev.visual_analysis_status || "");
							const isEdited = ev.derivation === "ADMIN_EDIT";

							return (
								<div
									key={ev.id}
									className={`p-4 transition-colors hover:bg-zinc-50/70 flex flex-col gap-2 ${
										needsReview ? "bg-amber-50/30" : ""
									}`}
								>
									<div className="flex items-center justify-between gap-3">
										<div className="flex flex-wrap items-center gap-2">
											<span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-700">
												#{ev.ordinal}
											</span>
											<span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-100">
												{ev.evidence_type}
											</span>
											{ev.section_path && ev.section_path.length > 0 && (
												<span className="text-xs text-zinc-500 font-medium truncate max-w-xs">
													{ev.section_path.join(" / ")}
												</span>
											)}
											{isEdited && (
												<span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
													ADMIN EDIT (SSOT)
												</span>
											)}
											{ev.visual_analysis_status && (
												<span
													className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
														needsReview
															? "bg-amber-100 text-amber-900 border-amber-300 animate-pulse"
															: "bg-emerald-50 text-emerald-800 border-emerald-200"
													}`}
												>
													{ev.visual_analysis_status}
												</span>
											)}
										</div>

										<div className="flex items-center gap-1.5 shrink-0">
											{needsReview && (
												<Button
													size="sm"
													variant="outline"
													onClick={() => handleResolve(ev.id)}
													disabled={resolveEvidenceMutation.isPending}
													className="h-7 text-xs border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 rounded-md px-2.5 shadow-none"
												>
													<RiCheckLine className="size-3.5 mr-1 text-amber-700" />
													Resolve Gate
												</Button>
											)}
											<Button
												size="sm"
												variant="ghost"
												onClick={() => handleOpenEdit(ev)}
												className="h-7 text-xs text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded-md px-2"
											>
												<RiEdit2Line className="size-3.5 mr-1" />
												Edit Evidence
											</Button>
										</div>
									</div>

									{ev.title && (
										<h5 className="text-xs font-bold text-zinc-900 mt-1">{ev.title}</h5>
									)}

									<p className="text-xs text-zinc-700 leading-relaxed font-mono bg-zinc-50/80 p-2.5 rounded-lg border border-zinc-100 whitespace-pre-wrap">
										{ev.body}
									</p>

									{ev.attributes && Object.keys(ev.attributes).length > 0 && (
										<div className="flex flex-wrap gap-1.5 mt-1">
											{Object.entries(ev.attributes).map(([k, v]) => (
												<span
													key={k}
													className="text-[10px] px-2 py-0.5 rounded bg-zinc-100 text-zinc-600 border border-zinc-200/60"
												>
													<strong className="text-zinc-800">{k}:</strong>{" "}
													{typeof v === "object" ? JSON.stringify(v) : String(v)}
												</span>
											))}
										</div>
									)}
								</div>
							);
						})
					)}
				</div>
			</div>

			{/* 5. Media Assets Gallery Card */}
			{qgData.assets && qgData.assets.length > 0 && (
				<div className="border border-zinc-200 rounded-xl bg-white overflow-hidden shadow-xs p-4">
					<div className="flex items-center justify-between pb-3 mb-3 border-b border-zinc-100">
						<div className="flex items-center gap-2">
							<RiImage2Line className="size-4.5 text-purple-600" />
							<h3 className="text-xs font-bold text-zinc-900 uppercase tracking-wider">
								Media Assets Audit ({qgData.assets.length} items)
							</h3>
						</div>
						<span className="text-[11px] text-zinc-500 font-medium">
							Multi-Signal Classifier Scored
						</span>
					</div>

					<div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
						{qgData.assets.map((ast) => (
							<div
								key={ast.id}
								className="border border-zinc-200 rounded-lg p-3 bg-zinc-50/60 flex flex-col justify-between gap-2"
							>
								<div className="flex items-center justify-between gap-2">
									<span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-100 text-purple-800 border border-purple-200">
										{ast.asset_class}
									</span>
									<span className="text-[10px] font-semibold text-zinc-600">
										Score: {ast.classification_score}
									</span>
								</div>

								<div className="text-xs text-zinc-800 font-medium truncate" title={ast.label || ast.storage_key}>
									{ast.label || ast.storage_key.split("/").pop()}
								</div>

								<div className="flex items-center justify-between text-[10px] text-zinc-500 pt-1 border-t border-zinc-200/60">
									<span>
										{ast.width && ast.height ? `${ast.width}x${ast.height} px` : "Dimension N/A"}
									</span>
									<span className="uppercase font-semibold text-emerald-700">{ast.status}</span>
								</div>
							</div>
						))}
					</div>
				</div>
			)}

			{/* 6. Inline Evidence Edit Modal (D1-a) */}
			{editingEvidence && (
				<div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
					<div className="bg-white rounded-2xl border border-zinc-200 shadow-xl max-w-xl w-full p-5 flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150">
						<div className="flex items-center justify-between pb-3 border-b border-zinc-100">
							<div>
								<h3 className="text-sm font-bold text-zinc-900">
									Edit Canonical Evidence (D1-a SSOT)
								</h3>
								<p className="text-xs text-zinc-500 mt-0.5">
									Perubahan akan menandai derivation sebagai ADMIN_EDIT dan menghitung ulang hash SHA-256.
								</p>
							</div>
							<button
								onClick={() => setEditingEvidence(null)}
								className="text-zinc-400 hover:text-zinc-700 p-1 rounded-md"
							>
								<RiCloseLine className="size-5" />
							</button>
						</div>

						<div className="flex flex-col gap-3">
							<div>
								<label className="text-xs font-semibold text-zinc-700 block mb-1">
									Judul / Header Unit
								</label>
								<input
									type="text"
									value={editTitle}
									onChange={(e) => setEditTitle(e.target.value)}
									placeholder="Judul Section / Nama Produk..."
									className="w-full text-xs px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-600"
								/>
							</div>

							<div>
								<label className="text-xs font-semibold text-zinc-700 block mb-1">
									Fakta Klinis / Deskripsi Evidence (Teks Kanonik)
								</label>
								<textarea
									rows={5}
									value={editBody}
									onChange={(e) => setEditBody(e.target.value)}
									placeholder="Isi fakta klinis..."
									className="w-full text-xs font-mono p-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-600 resize-y"
								/>
							</div>

							<div>
								<label className="text-xs font-semibold text-zinc-700 block mb-1">
									Attributes JSON (Indikasi, Dosis, Nilai Efikasi)
								</label>
								<textarea
									rows={3}
									value={editAttributesStr}
									onChange={(e) => setEditAttributesStr(e.target.value)}
									placeholder="{ ... }"
									className="w-full text-[11px] font-mono p-2.5 border border-zinc-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-600"
								/>
							</div>
						</div>

						<div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-100">
							<Button
								variant="outline"
								size="sm"
								onClick={() => setEditingEvidence(null)}
								className="h-8 text-xs rounded-lg"
							>
								Batal
							</Button>
							<Button
								size="sm"
								onClick={handleSaveEvidence}
								disabled={updateEvidenceMutation.isPending || !editBody.trim()}
								className="h-8 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-none"
							>
								{updateEvidenceMutation.isPending ? "Menyimpan..." : "Simpan Koreksi SSOT"}
							</Button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
