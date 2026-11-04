"use client";

import { ChatPreview } from "@/app/dashboard/knowledge/components/preview/chat-preview";
import { QualityGatePanel } from "@/app/dashboard/knowledge/components/preview/quality-gate-panel";
import { IngestSuccessModal } from "@/app/dashboard/knowledge/components/preview/ingest-success-modal";
import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { Button } from "@/components/ui/button";
import {
	RiArrowLeftLine,
	RiDeleteBin7Line,
	RiEdit2Line,
	RiCheckLine,
	RiStopCircleLine,
	RiAlertLine,
	RiLoader4Line,
	RiFileList3Line,
	RiShieldCheckLine,
	RiDownload2Line,
} from "@remixicon/react";

import { use, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import {
	useDeleteKnowledge,
	useKnowledgeDetail,
	useEditKnowledge,
	connectionLost,
	useApproveKnowledge,
	useQualityGate,
} from "../hooks/use-knowledge";
import { useSession } from "@/hooks/use-session";
import { useSafeBack } from "@/hooks/use-safe-back";
import { VisibilitySettings, KnowledgeChunkItem, extractKnowledgeCategories } from "../api/types";
import { KnowledgeDetailSkeleton } from "./knowledge-detail-skeleton";

export default function KnowledgeDetailPage({ params }: { params: Promise<{ id: string }> }) {
	const unwrappedParams = use(params);
	const id = unwrappedParams.id;
	const searchParams = useSearchParams();
	const initialEdit = searchParams.get("edit") === "true";
	const { data, isLoading, error } = useKnowledgeDetail(id);
	const { data: qgData } = useQualityGate(id, { summaryOnly: true });
	const [currentView, setCurrentView] = useState<"preview" | "quality-gate">("preview");
	const deleteMutation = useDeleteKnowledge();
	const { user } = useSession();
	const docStatus = (data?.status || "").toUpperCase();
	const hasWriteAccess = user?.accesses?.includes("knowledge:write") || user?.type === "STAFF" || user?.type === "ADMIN" || user?.roles?.some((r) => r.name.toLowerCase().includes("admin")) || !user;
	const hasDeleteAccess = user?.accesses?.includes("knowledge:delete") || user?.type === "STAFF" || user?.type === "ADMIN" || user?.roles?.some((r) => r.name.toLowerCase().includes("admin")) || !user;
	const [isEditMode, setIsEditMode] = useState(initialEdit);
	const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
	const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
	const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
	const [isApproveModalOpen, setIsApproveModalOpen] = useState(false);
	const [isSuccessModalOpen, setIsSuccessModalOpen] = useState(false);
	const editKnowledge = useEditKnowledge();
	const approveKnowledge = useApproveKnowledge();

	const fallbackPath = data?.project_id
		? `/dashboard/knowledge/project/${data.project_id}`
		: "/dashboard/knowledge";
	const handleBack = useSafeBack(fallbackPath);

	const initialCategories = extractKnowledgeCategories(data);
	const initialVisibility = (data?.metadata?.visibility_settings as VisibilitySettings) || { clinics: ["all"], doctor_types: ["all"], doctors: ["all"] };
	const initialChunks = (data?.metadata?.chunks as KnowledgeChunkItem[]) || [];
	
	const [pendingCategories, setPendingCategories] = useState<string[]>(initialCategories);
	const [pendingVisibilitySettings, setPendingVisibilitySettings] = useState<VisibilitySettings>(initialVisibility);
	const [pendingTitle, setPendingTitle] = useState(data?.title || "");
	const [pendingSummary, setPendingSummary] = useState(data?.ai_summary || "");
	const [pendingChunks, setPendingChunks] = useState<KnowledgeChunkItem[]>(initialChunks);

	useEffect(() => {
		if (!isEditMode && data) {
			const cats = extractKnowledgeCategories(data);
			const vis = (data.metadata?.visibility_settings as VisibilitySettings) || { clinics: ["all"], doctor_types: ["all"], doctors: ["all"] };
			const chunks = (data.metadata?.chunks as KnowledgeChunkItem[]) || [];
			setPendingCategories(cats);
			setPendingVisibilitySettings(vis);
			if (data.title) setPendingTitle(data.title);
			if (data.ai_summary) setPendingSummary(data.ai_summary);
			if (chunks.length > 0) setPendingChunks(chunks);
		}
	}, [data?.id, data?.title, data?.ai_summary, data?.metadata, isEditMode]);

	const handleDelete = async () => {
		await deleteMutation.mutateAsync(id);
		handleBack();
	};

	const formatDisplayTitle = (raw: string | undefined) => {
		if (!raw) return "Knowledge Document";
		return raw
			.replace(/\.[^/.]+$/, "") // strip extension
			.replace(/[_-]/g, " ") // replace underscores/dashes with spaces
			.replace(/\b\w/g, (c) => c.toUpperCase()); // title case
	};

	const handleSave = async (newTitle?: string) => {
		try {
			await editKnowledge.mutateAsync({
				id,
				data: {
					summary: pendingSummary || data?.ai_summary || "",
					categories: pendingCategories,
					visibility_settings: pendingVisibilitySettings,
					title: typeof newTitle === "string" ? newTitle : pendingTitle,
					chunks: pendingChunks.length > 0 ? pendingChunks : undefined,
				},
			});
		} catch (error) {
			// The hook already told the user. A lost connection may still have saved: show the reloaded document;
			// any other failure keeps the edits open to correct and retry.
			if (connectionLost(error)) setIsEditMode(false);
			return;
		}
		setIsEditMode(false);
	};

	const handleApprove = async () => {
		try {
			if (
				(pendingCategories && pendingCategories.length > 0) ||
				pendingVisibilitySettings ||
				pendingTitle ||
				(pendingChunks && pendingChunks.length > 0) ||
				(pendingSummary && pendingSummary !== data?.ai_summary)
			) {
				await editKnowledge.mutateAsync({
					id,
					data: {
						summary: pendingSummary || data?.ai_summary || "",
						categories: pendingCategories,
						visibility_settings: pendingVisibilitySettings,
						title: pendingTitle,
						chunks: pendingChunks.length > 0 ? pendingChunks : undefined,
					},
					hideToast: true,
				});
			}
			await approveKnowledge.mutateAsync(id);
		} catch {
			// Reported by the mutation hooks (with a reload when the connection was lost)
			return;
		}
		if (typeof window !== "undefined") {
			localStorage.removeItem(`chat_preview_${id}`);
		}
		setIsSuccessModalOpen(true);
	};

	const handleCancel = () => {
		setPendingCategories(initialCategories);
		setPendingVisibilitySettings(initialVisibility);
		setPendingTitle(data?.title || "");
		setPendingSummary(data?.ai_summary || "");
		setPendingChunks(initialChunks);
		setIsEditMode(false);
	};

	if (isLoading && !data) {
		return <KnowledgeDetailSkeleton />;
	}

	if (error && !data) {
		return (
			<div className="flex flex-col items-center justify-center h-full gap-4 p-6 text-center">
				<div className="p-3 bg-red-50 text-red-600 rounded-full">
					<RiAlertLine className="size-8" />
				</div>
				<div>
					<h3 className="text-base font-semibold text-zinc-900">Gagal Memuat Dokumen</h3>
					<p className="text-sm text-zinc-500 mt-1 max-w-md">
						Dokumen mungkin telah dihapus, ID tidak valid, atau sesi login Anda telah berakhir.
					</p>
				</div>
				<Button
					variant="outline"
					size="sm"
					onClick={handleBack}
					className="rounded-lg text-zinc-700"
				>
					<RiArrowLeftLine className="size-4 mr-1.5" />
					Kembali ke Daftar Knowledge
				</Button>
			</div>
		);
	}

	return (
		<div className="flex flex-col h-[calc(100vh-65px)] w-full bg-white relative">
			{/* Title Header with Actions */}
			<div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 shrink-0 bg-white justify-between">
				<div className="flex items-center gap-3 flex-1 min-w-0 mr-4">
					<Button
						variant="ghost"
						size="icon"
						onClick={handleBack}
						className="size-9 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 shrink-0"
						title="Back"
						aria-label="Back"
					>
						<RiArrowLeftLine className="size-5" />
					</Button>
					<div className="flex items-center gap-3 flex-1 min-w-0 max-w-xl">
						<h1 className="text-base font-semibold text-zinc-900 truncate" title={formatDisplayTitle(isEditMode ? (pendingTitle || data?.title) : data?.title)}>
							{formatDisplayTitle(isEditMode ? (pendingTitle || data?.title) : data?.title)}
						</h1>
						{data?.uploaded_by_name && (
							<div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-gray-50 border border-gray-200 px-2.5 py-1 rounded-md shrink-0">
								<span>Uploaded by:</span>
								<span className="font-medium text-zinc-800">{data.uploaded_by_name}</span>
							</div>
						)}
						{data?.status === "APPROVED" && data?.approved_at && (
							<div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-gray-50 border border-gray-200 px-2.5 py-1 rounded-md shrink-0">
								<span>Approved at:</span>
								<span className="font-medium text-zinc-800">
									{new Date(data.approved_at).toLocaleDateString("id-ID", {
										day: "2-digit",
										month: "short",
										year: "numeric",
										hour: "2-digit",
										minute: "2-digit",
									})}{" "}
									WIB
								</span>
							</div>
						)}
					</div>
				</div>

				{/* Center: View Switcher (Preview vs Quality Gate) */}
				<div className="flex items-center gap-1 bg-zinc-100 p-1 rounded-lg border border-zinc-200">
					<button
						type="button"
						onClick={() => setCurrentView("preview")}
						className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer ${
							currentView === "preview"
								? "bg-white text-zinc-900 shadow-xs"
								: "text-zinc-600 hover:text-zinc-900"
						}`}
					>
						<RiFileList3Line className="size-3.5" />
						Preview & Chat
					</button>
					<button
						type="button"
						onClick={() => setCurrentView("quality-gate")}
						className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer ${
							currentView === "quality-gate"
								? "bg-white text-zinc-900 shadow-xs"
								: "text-zinc-600 hover:text-zinc-900"
						}`}
					>
						<RiShieldCheckLine className="size-3.5 text-blue-600" />
						Quality Gate & Observability (D9)
						{qgData?.readiness && (
							<span
								className={`ml-1 text-[10px] font-bold px-1.5 py-0.2 rounded-full ${
									qgData.readiness.is_ready
										? "bg-emerald-100 text-emerald-800"
										: "bg-amber-100 text-amber-800 animate-pulse"
								}`}
							>
								{qgData.readiness.is_ready ? "Ready" : `${qgData.readiness.unresolved_items} Review`}
							</span>
						)}
					</button>
				</div>

				<div className="flex items-center gap-2">
					<Button
						variant="outline"
						onClick={() => window.open(`/api/knowledge/${id}/file`, "_blank")}
						className="gap-2 border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-3.5 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						title="View / Download original uploaded file"
					>
						<RiDownload2Line className="size-4 text-zinc-500" />
						View Original File
					</Button>
					{docStatus === "PROCESSING" && (
						<Button
							onClick={() => setIsCancelModalOpen(true)}
							disabled={deleteMutation.isPending || isLoading}
							variant="outline"
							className="gap-2 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50 hover:border-red-300 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						>
							<RiStopCircleLine className="size-4" />
							Cancel Ingestion
						</Button>
					)}
					{(hasDeleteAccess || docStatus === "REJECTED" || docStatus === "PENDING" || docStatus === "PROCESSING") && (
						<Button
							onClick={() => setIsDeleteModalOpen(true)}
							disabled={deleteMutation.isPending || isLoading}
							variant="outline"
							className="gap-2 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50 hover:border-red-300 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
						>
							<RiDeleteBin7Line className="size-4" />
							{docStatus === "REJECTED" ? "Delete Record" : "Delete Knowledge"}
						</Button>
					)}
					{hasWriteAccess && docStatus === "PENDING" && (
						<Button
							onClick={() => {
								if (qgData?.readiness && !qgData.readiness.is_ready) {
									setCurrentView("quality-gate");
								} else {
									setIsApproveModalOpen(true);
								}
							}}
							disabled={isLoading || approveKnowledge.isPending || editKnowledge.isPending}
							className={`gap-2 rounded-lg shadow-none h-10 px-4 font-medium text-sm transition-colors cursor-pointer text-white ${
								qgData?.readiness && !qgData.readiness.is_ready
									? "bg-amber-600 hover:bg-amber-700"
									: "bg-blue-600 hover:bg-blue-700"
							}`}
							title={
								qgData?.readiness && !qgData.readiness.is_ready
									? "Knowledge Readiness Gate (D9): Ada item yang membutuhkan review Admin sebelum approve"
									: undefined
							}
						>
							{approveKnowledge.isPending || editKnowledge.isPending ? (
								<>
									<RiLoader4Line className="size-4 animate-spin" />
									Indexing...
								</>
							) : qgData?.readiness && !qgData.readiness.is_ready ? (
								<>
									<RiAlertLine className="size-4" />
									Review Required ({qgData.readiness.unresolved_items})
								</>
							) : (
								<>
									<RiCheckLine className="size-4" />
									Approve Knowledge
								</>
							)}
						</Button>
					)}
					{hasWriteAccess && (docStatus === "APPROVED" || !docStatus) && (
						<div className="flex items-center gap-2">
							{isEditMode && (
								<Button
									variant="outline"
									className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg shadow-none h-10 px-4 font-medium text-sm transition-colors cursor-pointer"
									disabled={isLoading || editKnowledge.isPending}
									onClick={handleCancel}
								>
									Cancel
								</Button>
							)}
							<Button
								variant={isEditMode ? "default" : "outline"}
								className={`gap-2 ${isEditMode ? "bg-blue-600 hover:bg-blue-700 text-white" : "border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50"} rounded-lg shadow-none h-10 px-4 font-medium text-sm transition-colors cursor-pointer`}
								disabled={isLoading || editKnowledge.isPending}
								onClick={() => {
									if (isEditMode) {
										setIsSaveModalOpen(true);
									} else {
										setPendingSummary(data?.ai_summary || "");
										setIsEditMode(true);
									}
								}}
							>
								{isEditMode ? <RiCheckLine className="size-4" /> : <RiEdit2Line className="size-4" />}
								{isEditMode ? "Save Knowledge" : "Edit Knowledge"}
							</Button>
						</div>
					)}

				</div>
			</div>

			{/* Main Content Area */}
			<div className="flex flex-1 overflow-hidden">
				{currentView === "preview" ? (
					<ChatPreview
						knowledgeId={id}
						knowledge={data}
						knowledgeStatus={data?.status}
						aiSummary={pendingSummary || data?.ai_summary}
						summaryValue={pendingSummary}
						onChangeSummary={setPendingSummary}
						fileName={data?.file_name}
						initialPrompt={(data?.metadata?.initial_prompt as string) || undefined}
						files={(data?.metadata?.files as { file_name: string; summary: string }[]) || []}
						isDetailLoading={isLoading}
						isEditMode={isEditMode}
						categories={pendingCategories}
						onChangeCategories={setPendingCategories}
						chunks={pendingChunks}
						visibilitySettings={pendingVisibilitySettings}
						onChangeVisibilitySettings={setPendingVisibilitySettings}
						title={pendingTitle}
						onChangeTitle={setPendingTitle}
						onSave={() => setIsSaveModalOpen(true)}
					/>
				) : (
					<div className="flex-1 overflow-y-auto bg-zinc-50/50">
						<QualityGatePanel
							knowledgeId={id}
							isEditMode={isEditMode}
							onSummaryRegenerated={(newSummary) => {
								setPendingSummary(newSummary);
								setCurrentView("preview");
							}}
						/>
					</div>
				)}
			</div>

			{/* Save Knowledge Confirmation Modal (For Approved Docs) */}
			<ConfirmationModal
				isOpen={isSaveModalOpen}
				onOpenChange={setIsSaveModalOpen}
				title="Save Knowledge?"
				description="Are you sure you want to save the changes of the knowledge? If you confirm, it will be implemented into the chatbot."
				confirmText="Save Knowledge"
				cancelText="Cancel"
				isLoading={editKnowledge.isPending}
				onConfirm={handleSave}
			/>

			{/* Approve Knowledge Confirmation Modal (For Pending Docs) */}
			<ConfirmationModal
				isOpen={isApproveModalOpen}
				onOpenChange={setIsApproveModalOpen}
				title="Save Knowledge?"
				description="Are you sure you want to save the changes of the knowledge? If you confirm, it will be implemented into the chatbot."
				confirmText="Save Knowledge"
				cancelText="Cancel"
				isLoading={approveKnowledge.isPending || editKnowledge.isPending}
				onConfirm={handleApprove}
			/>

			{/* Ingest Success Modal */}
			<IngestSuccessModal
				isOpen={isSuccessModalOpen}
				onOpenChange={setIsSuccessModalOpen}
				title="Knowledge Ingested Successfully"
				description="Now the knowledge that you uploaded and approved already added to the system"
				buttonText="View Knowledge"
				onAction={() => {
					handleBack();
				}}
			/>

			{/* Cancel Ingestion Confirmation Modal */}
			<ConfirmationModal
				isOpen={isCancelModalOpen}
				onOpenChange={setIsCancelModalOpen}
				title="Cancel Ingestion?"
				description="Are you sure you want to cancel the ingestion process for this document? The pending draft and temporary files will be discarded."
				confirmText="Cancel Ingestion"
				cancelText="Keep Processing"
				isLoading={deleteMutation.isPending}
				onConfirm={handleDelete}
			/>

			{/* Delete Knowledge Confirmation Modal */}
			<ConfirmationModal
				isOpen={isDeleteModalOpen}
				onOpenChange={setIsDeleteModalOpen}
				title="Delete Knowledge?"
				description="Are you certain you want to delete this knowledge? If you proceed, it will be removed from the chatbot."
				confirmText="Delete Knowledge"
				cancelText="Cancel"
				isLoading={deleteMutation.isPending}
				onConfirm={handleDelete}
			/>
		</div>
	);
}
