"use client";

import {
	Attachment,
	AttachmentContent,
	AttachmentDescription,
	AttachmentMedia,
	AttachmentTitle,
} from "@/components/ui/attachment";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSession } from "@/hooks/use-session";
import { cn } from "@/lib/utils";
import {
	RiArrowDownSLine,
	RiArrowLeftLine,
	RiCheckLine,
	RiDeleteBin7Line,
	RiEdit2Line,
	RiFileExcel2Line,
	RiFilePdf2Line,
	RiFilePpt2Line,
	RiFileTextLine,
	RiFileWord2Line,
	RiImage2Line,
	RiStopCircleLine,
	RiEyeLine,
} from "@remixicon/react";
import { useRouter } from "next/navigation";
import { use, useRef, useState } from "react";
import { toast } from "sonner";
import { useSafeBack } from "@/hooks/use-safe-back";
import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { IngestSuccessModal } from "@/app/dashboard/knowledge/components/preview/ingest-success-modal";
import {
	useApproveBatchKnowledge,
	useDeleteKnowledge,
	useKnowledgeBatch,
} from "../../hooks/use-knowledge";
import { VisibilitySettings } from "../../api/types";
import { BatchKnowledgeTabContent, BatchTabHandle } from "./BatchKnowledgeTabContent";
import { BatchDocumentTabs } from "./BatchDocumentTabs";
import { BatchExecutiveSummary } from "./BatchExecutiveSummary";
import { BatchVisibilityModal } from "./BatchVisibilityModal";
import { BatchReviewSkeleton } from "./batch-review-skeleton";

export default function BatchKnowledgePage({ params }: { params: Promise<{ id: string }> }) {
	const router = useRouter();
	const handleBack = useSafeBack("/dashboard/knowledge");
	const unwrappedParams = use(params);
	const batchId = unwrappedParams.id;
	const { data: batchDocuments, isLoading, error } = useKnowledgeBatch(batchId);
	const [activeTab, setActiveTab] = useState<string | undefined>(undefined);
	const { user } = useSession();
	const hasWriteAccess = user?.accesses?.includes("knowledge:write") || user?.type === "STAFF" || user?.type === "ADMIN" || user?.roles?.some((r) => r.name.toLowerCase().includes("admin")) || !user;
	const hasDeleteAccess = user?.accesses?.includes("knowledge:delete") || user?.type === "STAFF" || user?.type === "ADMIN" || user?.roles?.some((r) => r.name.toLowerCase().includes("admin")) || !user;
	const deleteMutation = useDeleteKnowledge();
	const approveBatchMutation = useApproveBatchKnowledge();

	const [isApproveAllOpen, setIsApproveAllOpen] = useState(false);
	const [isSuccessOpen, setIsSuccessOpen] = useState(false);
	const [isCancelDocOpen, setIsCancelDocOpen] = useState(false);
	const [isDeleteDocOpen, setIsDeleteDocOpen] = useState(false);
	const [isBatchVisibilityOpen, setIsBatchVisibilityOpen] = useState(false);
	const [isSummaryExpanded, setIsSummaryExpanded] = useState(true);
	const [editModes, setEditModes] = useState<Record<string, boolean>>({});
	const tabRefs = useRef<Record<string, BatchTabHandle | null>>({});

	if (error) {
		return (
			<div className="flex items-center justify-center h-full text-red-500">
				Error loading batch details
			</div>
		);
	}

	if (isLoading || !batchDocuments) {
		return <BatchReviewSkeleton />;
	}

	if (batchDocuments.length === 0) {
		return (
			<div className="flex items-center justify-center h-full text-zinc-500">
				No documents found for this batch.
			</div>
		);
	}

	const currentTab = activeTab || batchDocuments[0].id;
	const activeDoc = batchDocuments.find((d) => d.id === currentTab) || batchDocuments[0];
	const activeDocStatus = (activeDoc?.status || "").toUpperCase();

	// Batch summary from metadata if available
	const batchSummary = batchDocuments[0]?.metadata?.batch_summary as string | undefined;
	const fallbackFeedbacks = batchDocuments
		.map((d, i) => {
			const feedback =
				(d.metadata?.refine_feedback as string) || (d.metadata?.ai_refine_feedback as string) || "";
			if (!feedback) return null;
			const title = d.title || `Document ${i + 1}`;
			return `- **${title}**:\n  ${feedback.trim()}`;
		})
		.filter(Boolean);

	const displayedSummary =
		batchSummary || (fallbackFeedbacks.length > 0 ? fallbackFeedbacks.join("\n\n") : undefined);

	const isEditMode = editModes[currentTab] || false;
	const hasApprovableDocs = batchDocuments.some((d) => (d.status || "").toUpperCase() === "PENDING");

	const handleEditToggle = () => {
		if (isEditMode) {
			if (tabRefs.current[currentTab]) {
				tabRefs.current[currentTab]?.triggerSave();
			}
		} else {
			setEditModes((prev) => ({ ...prev, [currentTab]: true }));
		}
	};

	const handleDelete = async () => {
		await tabRefs.current[currentTab]?.handleDelete();
	};

	const handleDeleteSuccess = (deletedId: string) => {
		const remaining = batchDocuments.filter((d) => d.id !== deletedId);
		if (remaining.length === 0) {
			router.push("/dashboard/knowledge");
		} else {
			setActiveTab(remaining[0].id);
		}
	};

	const getFileIconAndColor = (filename?: string | null) => {
		if (!filename)
			return { Icon: RiFileTextLine, bgColor: "bg-blue-50", textColor: "text-blue-600" };
		const ext = filename.split(".").pop()?.toLowerCase() || "";
		switch (ext) {
			case "pdf":
				return { Icon: RiFilePdf2Line, bgColor: "bg-red-50", textColor: "text-red-600" };
			case "doc":
			case "docx":
				return {
					Icon: RiFileWord2Line,
					bgColor: "bg-blue-50",
					textColor: "text-blue-600",
				};
			case "xls":
			case "xlsx":
			case "csv":
				return {
					Icon: RiFileExcel2Line,
					bgColor: "bg-emerald-50",
					textColor: "text-emerald-600",
				};
			case "ppt":
			case "pptx":
			case "pps":
			case "ppsx":
			case "pot":
			case "potx":
			case "odp":
				return {
					Icon: RiFilePpt2Line,
					bgColor: "bg-orange-50",
					textColor: "text-orange-600",
				};
			case "png":
			case "jpg":
			case "jpeg":
			case "gif":
			case "webp":
				return {
					Icon: RiImage2Line,
					bgColor: "bg-purple-50",
					textColor: "text-purple-600",
				};
			case "txt":
			default:
				return {
					Icon: RiFileTextLine,
					bgColor: "bg-blue-50",
					textColor: "text-blue-600",
				};
		}
	};

	return (
		<div className="flex flex-col h-full bg-white relative">
			{/* Header */}
			<div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-200 justify-between bg-white/50 backdrop-blur-sm z-10 sticky top-0">
				<div className="flex items-center gap-3 min-w-0">
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
					<h1 className="text-base font-semibold text-zinc-900 shrink-0">Batch Review Session</h1>

					<div className="h-4 w-px bg-zinc-200 shrink-0 hidden sm:block" />

					{/* Header Document Picker Dropdown */}
					<DropdownMenu>
						{(() => {
							const { Icon: ActiveIcon, textColor: activeTextColor } = getFileIconAndColor(
								activeDoc?.file_name || activeDoc?.title,
							);
							return (
								<DropdownMenuTrigger className="inline-flex items-center justify-between h-9 text-xs sm:text-sm font-medium gap-2 text-zinc-700 bg-white hover:bg-zinc-50 border border-gray-200 px-3 rounded-lg cursor-pointer transition-colors shadow-none w-72 sm:w-80 shrink-0">
									<div className="flex items-center gap-2 min-w-0 flex-1 text-left">
										<ActiveIcon className={cn("size-4 shrink-0", activeTextColor)} />
										<span className="truncate">
											{activeDoc?.file_name ||
												activeDoc?.title ||
												`Document ${batchDocuments.findIndex((d) => d.id === currentTab) + 1}`}
										</span>
									</div>
									<span className="text-xs text-zinc-400 shrink-0 font-normal">
										({batchDocuments.findIndex((d) => d.id === currentTab) + 1}/
										{batchDocuments.length})
									</span>
									<RiArrowDownSLine className="size-4 text-zinc-400 shrink-0 ml-0.5" />
								</DropdownMenuTrigger>
							);
						})()}
						<DropdownMenuContent
							align="start"
							className="w-72 sm:w-80 max-h-80 overflow-y-auto rounded-lg border border-gray-200 p-1.5 shadow-none bg-white"
						>
							{batchDocuments.map((doc, idx) => {
								const { Icon: DocIcon, textColor: docTextColor } = getFileIconAndColor(
									doc.file_name || doc.title,
								);
								return (
									<DropdownMenuItem
										key={doc.id}
										onClick={() => setActiveTab(doc.id)}
										className={cn(
											"flex items-center justify-between gap-2 text-xs py-2 px-2.5 rounded-lg cursor-pointer transition-colors",
											doc.id === currentTab
												? "bg-blue-50 text-blue-900 font-medium"
												: "hover:bg-zinc-50",
										)}
									>
										<div className="flex items-center gap-2 min-w-0 flex-1">
											<span className="text-[11px] text-zinc-500 font-mono w-4 shrink-0">
												{idx + 1}.
											</span>
											<DocIcon className={cn("size-3.5 shrink-0", docTextColor)} />
											<span
												className="truncate"
												title={doc.file_name || doc.title || `Document ${idx + 1}`}
											>
												{doc.file_name || doc.title || `Document ${idx + 1}`}
											</span>
										</div>
										<div className="shrink-0">
											{(doc.status || "").toUpperCase() === "PROCESSING" && (
												<Badge className="bg-blue-50 text-blue-700 border-blue-200 text-[10px] px-1.5 py-0 rounded-md shadow-none">
													Processing
												</Badge>
											)}
											{(doc.status || "").toUpperCase() === "PENDING" && (
												<Badge className="bg-amber-50 text-amber-700 border-amber-200 text-[10px] px-1.5 py-0 rounded-md shadow-none">
													Review
												</Badge>
											)}
											{(doc.status || "").toUpperCase() === "APPROVED" && (
												<Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] px-1.5 py-0 rounded-md shadow-none">
													Approved
												</Badge>
											)}
											{(doc.status || "").toUpperCase() === "REJECTED" && (
												<Badge className="bg-red-50 text-red-700 border-red-200 text-[10px] px-1.5 py-0 rounded-md shadow-none">
													Failed
												</Badge>
											)}
										</div>
									</DropdownMenuItem>
								);
							})}
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
				<div className="flex items-center gap-2">
					{hasDeleteAccess && activeDocStatus === "PROCESSING" && (
						<Button
							variant="outline"
							className="gap-2 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50 hover:border-red-300 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
							onClick={() => setIsCancelDocOpen(true)}
							disabled={deleteMutation.isPending || isLoading}
						>
							<RiStopCircleLine className="size-4" />
							Cancel Ingestion
						</Button>
					)}
					{hasDeleteAccess &&
						(activeDocStatus === "PENDING" || activeDocStatus === "REJECTED" || activeDocStatus === "PROCESSING") && (
							<Button
								variant="outline"
								className="gap-2 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50 hover:border-red-300 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
								onClick={() => setIsDeleteDocOpen(true)}
								disabled={deleteMutation.isPending || isLoading}
							>
								<RiDeleteBin7Line className="size-4" />
								Delete Document
							</Button>
						)}
					{hasDeleteAccess && activeDocStatus === "APPROVED" && (
						<Button
							variant="outline"
							className="gap-2 border-red-200 text-red-600 hover:text-red-700 hover:bg-red-50 hover:border-red-300 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
							onClick={handleDelete}
							disabled={deleteMutation.isPending || isLoading}
						>
							<RiDeleteBin7Line className="size-4" />
							Delete Knowledge
						</Button>
					)}
					{hasWriteAccess && (activeDocStatus === "APPROVED" || !activeDocStatus) && (
						<div className="flex items-center gap-2">
							{isEditMode && (
								<Button
									variant="outline"
									className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
									disabled={isLoading}
									onClick={() => {
										tabRefs.current[currentTab]?.handleCancel();
										setEditModes((prev) => ({ ...prev, [currentTab]: false }));
									}}
								>
									Cancel
								</Button>
							)}
							<Button
								variant={isEditMode ? "default" : "outline"}
								className={`gap-2 ${isEditMode ? "bg-blue-600 hover:bg-blue-700 text-white" : "border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50"} rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none`}
								disabled={isLoading}
								onClick={handleEditToggle}
							>
								{isEditMode ? <RiCheckLine className="size-4" /> : <RiEdit2Line className="size-4" />}
								{isEditMode ? "Save Knowledge" : "Edit Knowledge"}
							</Button>
						</div>
					)}
					{hasWriteAccess && hasApprovableDocs && (
						<Button
							variant="default"
							className="gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
							disabled={isLoading || approveBatchMutation.isPending}
							onClick={() => setIsApproveAllOpen(true)}
						>
							<RiCheckLine className="size-4" />
							Approve All
						</Button>
					)}
				</div>
			</div>

			{/* Active Tab View */}
			<div className="flex-1 overflow-hidden flex flex-col w-full">
				<div className="flex-1 overflow-hidden relative">
					{(() => {
						const preHeaderNode = (
							<div className="flex flex-row flex-wrap justify-end gap-2 mb-4 self-end max-h-36 overflow-y-auto w-full min-w-0 max-w-full pr-1">
								{batchDocuments.map((tabDoc) => {
									const fileName = tabDoc.file_name || tabDoc.title || "Document";
									const { Icon, bgColor, textColor } = getFileIconAndColor(fileName);
									return (
										<Attachment
											key={tabDoc.id}
											className="bg-white border border-zinc-200/90 shadow-none p-1.5 w-48 sm:w-56 shrink-0 rounded-lg flex items-center"
										>
											<AttachmentMedia
												className={`${bgColor} ${textColor} shrink-0 rounded-md p-2`}
											>
												<Icon className="size-4" />
											</AttachmentMedia>
											<AttachmentContent className="overflow-hidden min-w-0 pr-1.5">
												<AttachmentTitle className="text-[12px] font-medium text-zinc-950 truncate block">
													{fileName}
												</AttachmentTitle>
												<AttachmentDescription className="text-[10px] text-zinc-500 uppercase font-mono">
													{fileName.split(".").pop() || "FILE"}
												</AttachmentDescription>
											</AttachmentContent>
										</Attachment>
									);
								})}
							</div>
						);

						const headerNode = (
							<div className="flex flex-col gap-4 mb-4 w-full min-w-0 max-w-full">
								{/* Batch Summary Box if present */}
								{displayedSummary ? (
									<BatchExecutiveSummary
										summary={displayedSummary}
										documentCount={batchDocuments.length}
										isExpanded={isSummaryExpanded}
										onToggleExpand={() => setIsSummaryExpanded((prev) => !prev)}
										onSetVisibility={() => setIsBatchVisibilityOpen(true)}
										hasWriteAccess={hasWriteAccess}
									/>
								) : (
									hasWriteAccess && (
										<div className="flex items-center justify-between gap-3 p-3.5 bg-zinc-50 border border-zinc-200/80 rounded-lg shadow-none">
											<div className="flex items-center gap-2">
												<RiEyeLine className="size-4 text-zinc-500" />
												<span className="text-xs sm:text-sm text-zinc-600 font-medium">
													Set branch, doctor type, or doctor access limits for all documents in this batch:
												</span>
											</div>
											<Button
												type="button"
												size="default"
												variant="default"
												onClick={() => setIsBatchVisibilityOpen(true)}
												className="gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none shrink-0"
											>
												<RiEyeLine className="size-4" />
												Set Visibility
											</Button>
										</div>
									)
								)}

								{/* Batch Documents Tabs Bar */}
								<BatchDocumentTabs
									documents={batchDocuments}
									activeId={currentTab}
									onSelectDoc={setActiveTab}
								/>
							</div>
						);

						return (
							<div key={activeDoc.id} className="absolute inset-0 m-0 flex flex-col bg-white">
								<BatchKnowledgeTabContent
									key={activeDoc.id}
									knowledgeId={activeDoc.id}
									initialKnowledge={activeDoc}
									ref={(el) => {
										tabRefs.current[activeDoc.id] = el;
									}}
									isEditMode={editModes[activeDoc.id] || false}
									setIsEditMode={(v) => setEditModes((prev) => ({ ...prev, [activeDoc.id]: v }))}
									headerNode={headerNode}
									preHeaderNode={preHeaderNode}
									onDeleteSuccess={handleDeleteSuccess}
								/>
							</div>
						);
					})()}
				</div>
			</div>

			{/* Cancel Ingestion Confirmation Modal */}
			<ConfirmationModal
				isOpen={isCancelDocOpen}
				onOpenChange={setIsCancelDocOpen}
				title="Cancel Ingestion?"
				description={`Are you sure you want to cancel the ingestion process for "${activeDoc?.file_name || activeDoc?.title || "this document"}"? The pending draft will be discarded.`}
				confirmText="Cancel Ingestion"
				cancelText="Keep Processing"
				variant="destructive"
				isLoading={deleteMutation.isPending}
				onConfirm={async () => {
					await deleteMutation.mutateAsync(currentTab);
					setIsCancelDocOpen(false);
					toast.success("Ingestion cancelled successfully.");
					handleDeleteSuccess(currentTab);
				}}
			/>

			{/* Delete Document Confirmation Modal */}
			<ConfirmationModal
				isOpen={isDeleteDocOpen}
				onOpenChange={setIsDeleteDocOpen}
				title="Delete Document?"
				description={`Are you sure you want to delete "${activeDoc?.file_name || activeDoc?.title || "this document"}" from the batch?`}
				confirmText="Delete Document"
				cancelText="Cancel"
				variant="destructive"
				isLoading={deleteMutation.isPending}
				onConfirm={async () => {
					await deleteMutation.mutateAsync(currentTab);
					setIsDeleteDocOpen(false);
					toast.success("Document removed from batch.");
					handleDeleteSuccess(currentTab);
				}}
			/>

			{/* Approve All Confirmation Modal */}
			<ConfirmationModal
				isOpen={isApproveAllOpen}
				onOpenChange={setIsApproveAllOpen}
				title="Approve All Documents"
				description={`Are you sure you want to approve and index all ${batchDocuments.length} document(s) in this batch into the AI Knowledge Base?`}
				confirmText="Approve All"
				isLoading={approveBatchMutation.isPending}
				onConfirm={async () => {
					await approveBatchMutation.mutateAsync(batchId);
					setIsSuccessOpen(true);
				}}
			/>

			{/* Batch Ingest Success Modal */}
			<IngestSuccessModal
				isOpen={isSuccessOpen}
				onOpenChange={setIsSuccessOpen}
				title="Batch Approved Successfully"
				description="All documents in this batch have been approved and indexed into the system."
				buttonText="Back to Knowledge Base"
				onAction={() => router.push("/dashboard/knowledge")}
			/>

			{/* Batch Visibility Settings Modal */}
			<BatchVisibilityModal
				isOpen={isBatchVisibilityOpen}
				onOpenChange={setIsBatchVisibilityOpen}
				batchId={batchId}
				documentCount={batchDocuments.length}
				initialSettings={
					(activeDoc?.metadata?.visibility_settings as VisibilitySettings) || {
						clinics: ["all"],
						doctor_types: ["all"],
						doctors: ["all"],
					}
				}
			/>
		</div>
	);
}
