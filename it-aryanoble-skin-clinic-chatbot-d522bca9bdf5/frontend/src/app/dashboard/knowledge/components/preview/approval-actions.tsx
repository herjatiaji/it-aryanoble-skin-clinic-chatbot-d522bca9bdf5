import { KnowledgeResponse, VisibilitySettings, KnowledgeChunkItem } from "@/app/dashboard/knowledge/api/types";
import {
	useApproveKnowledge,
	useEditKnowledge,
} from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { Button } from "@/components/ui/button";
import { RiCheckLine, RiLoader4Line } from "@remixicon/react";
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
	const { user } = useSession();
	const hasWriteAccess = user?.accesses?.includes("knowledge:write");
	const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
	const [isSuccessModalOpen, setIsSuccessModalOpen] = useState(false);

	if (!knowledge) return null;

	const handleApprove = async () => {
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
		if (typeof window !== "undefined") {
			localStorage.removeItem(`chat_preview_${knowledge.id}`);
		}
		setIsSuccessModalOpen(true);
	};

	return (
		<>
			{/* Manual Approval Action Card when status is PENDING */}
			{knowledge.status === "PENDING" && hasWriteAccess && (
				<div className="flex items-center justify-end gap-2 shrink-0 w-full pt-1">
					<Button
						type="button"
						size="default"
						onClick={() => setIsConfirmModalOpen(true)}
						disabled={approveKnowledge.isPending || editKnowledge.isPending}
						className="bg-blue-600 hover:bg-blue-700 text-white gap-2 cursor-pointer shadow-none rounded-lg px-4 h-10 font-medium text-sm ml-auto transition-colors"
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
