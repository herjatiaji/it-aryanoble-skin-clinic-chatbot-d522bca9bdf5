import { KnowledgeResponse, VisibilitySettings, KnowledgeChunkItem } from "@/app/dashboard/knowledge/api/types";
import {
	useApproveKnowledge,
	useEditKnowledge,
	useReparseVisionKnowledge,
} from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { Button } from "@/components/ui/button";
import { RiCheckLine, RiEyeLine, RiLoader4Line } from "@remixicon/react";
import { useSession } from "@/hooks/use-session";
import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { IngestSuccessModal } from "./ingest-success-modal";
import { useState } from "react";
import { useRouter } from "next/navigation";

interface ApprovalActionsProps {
	knowledge?: KnowledgeResponse;
	pendingCategories?: string[];
	pendingVisibilitySettings?: VisibilitySettings;
	pendingTitle?: string;
	pendingSummary?: string;
	pendingChunks?: KnowledgeChunkItem[];
}

export function ApprovalActions({
	knowledge,
	pendingCategories,
	pendingVisibilitySettings,
	pendingTitle,
	pendingSummary,
	pendingChunks,
}: ApprovalActionsProps) {
	const router = useRouter();
	const approveKnowledge = useApproveKnowledge();
	const editKnowledge = useEditKnowledge();
	const reparseVision = useReparseVisionKnowledge();
	const { user } = useSession();
	const hasWriteAccess = user?.accesses?.includes("knowledge:write");
	const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
	const [isReparseModalOpen, setIsReparseModalOpen] = useState(false);
	const [isSuccessModalOpen, setIsSuccessModalOpen] = useState(false);

	if (!knowledge) return null;

	const handleApprove = async () => {
		try {
			if (
				(pendingCategories && pendingCategories.length > 0) ||
				pendingVisibilitySettings ||
				pendingTitle ||
				(pendingChunks && pendingChunks.length > 0) ||
				(pendingSummary && pendingSummary !== knowledge.ai_summary)
			) {
				await editKnowledge.mutateAsync({
					id: knowledge.id,
					data: {
						summary: pendingSummary || knowledge.ai_summary || "",
						categories: pendingCategories || [],
						visibility_settings: pendingVisibilitySettings,
						title: pendingTitle,
						chunks: pendingChunks && pendingChunks.length > 0 ? pendingChunks : undefined,
					},
					hideToast: true,
				});
			}
			await approveKnowledge.mutateAsync(knowledge.id);
		} catch {
			// Reported by the mutation hooks (with a reload when the connection was lost)
			return;
		}
		if (typeof window !== "undefined") {
			localStorage.removeItem(`chat_preview_${knowledge.id}`);
		}
		setIsSuccessModalOpen(true);
	};

	const handleReparse = async () => {
		await reparseVision.mutateAsync({ id: knowledge.id });
		setIsReparseModalOpen(false);
	};

	return (
		<>
			{/* Manual Approval Action Card when status is PENDING */}
			{knowledge.status === "PENDING" && hasWriteAccess && (
				<div className="flex items-center justify-end gap-2 shrink-0 w-full pt-1">
					<Button
						type="button"
						variant="outline"
						size="default"
						onClick={() => setIsReparseModalOpen(true)}
						disabled={reparseVision.isPending || approveKnowledge.isPending || editKnowledge.isPending}
						className="border-blue-200 text-blue-700 hover:bg-blue-50/70 gap-2 cursor-pointer shadow-none rounded-lg px-4 h-10 font-medium text-sm transition-colors"
					>
						{reparseVision.isPending ? (
							<>
								<RiLoader4Line className="size-4 animate-spin" />
								Re-parsing with Vision...
							</>
						) : (
							<>
								<RiEyeLine className="size-4 text-blue-600" />
								Re-parse with Vision
							</>
						)}
					</Button>

					<Button
						type="button"
						size="default"
						onClick={() => setIsConfirmModalOpen(true)}
						disabled={reparseVision.isPending || approveKnowledge.isPending || editKnowledge.isPending}
						className="bg-blue-600 hover:bg-blue-700 text-white gap-2 cursor-pointer shadow-none rounded-lg px-4 h-10 font-medium text-sm transition-colors"
					>
						{approveKnowledge.isPending || editKnowledge.isPending ? (
							<>
								<RiLoader4Line className="size-4 animate-spin" />
								Indexing...
							</>
						) : (
							<>
								<RiCheckLine className="size-4" />
								Approve Knowledge
							</>
						)}
					</Button>
				</div>
			)}

			{/* Re-parse Confirmation Modal */}
			<ConfirmationModal
				isOpen={isReparseModalOpen}
				onOpenChange={setIsReparseModalOpen}
				title="Re-parse with Vision AI?"
				description="Dokumen ini akan diproses ulang menggunakan model Vision-native multimodal. Seluruh struktur slide, infografis, dan badge visual akan diekstraksi secara presisi."
				confirmText="Re-parse with Vision"
				cancelText="Cancel"
				isLoading={reparseVision.isPending}
				onConfirm={handleReparse}
			/>

			{/* Save Knowledge / Approve Confirmation Modal */}
			<ConfirmationModal
				isOpen={isConfirmModalOpen}
				onOpenChange={setIsConfirmModalOpen}
				title="Save Knowledge?"
				description="Are you sure you want to save the changes of the  knowledge? If you confirm, it will be implemented into the chatbot."
				confirmText="Save Knowledge"
				cancelText="Cancel"
				isLoading={approveKnowledge.isPending || editKnowledge.isPending}
				onConfirm={handleApprove}
			/>

			{/* Knowledge Ingested Successfully Modal */}
			<IngestSuccessModal
				isOpen={isSuccessModalOpen}
				onOpenChange={setIsSuccessModalOpen}
				title="Knowledge Ingested Successfully"
				description="Now the knowledge that you uploaded and approved already added to the system"
				buttonText="View Knowledge"
				onAction={() => {
					router.push("/dashboard/knowledge");
				}}
			/>
		</>
	);
}
