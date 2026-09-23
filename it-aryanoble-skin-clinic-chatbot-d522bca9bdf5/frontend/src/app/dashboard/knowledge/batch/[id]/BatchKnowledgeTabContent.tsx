"use client";

import { ChatPreview } from "@/app/dashboard/knowledge/components/preview/chat-preview";
import { ConfirmationModal } from "@/components/shared/confirmation-modal";
import { useState, useEffect, forwardRef, useImperativeHandle } from "react";
import {
	useKnowledgeDetail,
	useEditKnowledge,
	useDeleteKnowledge,
} from "../../hooks/use-knowledge";
import { KnowledgeResponse, VisibilitySettings, KnowledgeChunkItem, extractKnowledgeCategories } from "../../api/types";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

export interface BatchTabHandle {
	handleSave: (newTitle?: string) => Promise<void>;
	handleCancel: () => void;
	triggerSave: () => void;
	handleDelete: () => Promise<void>;
}

interface BatchKnowledgeTabContentProps {
	knowledgeId: string;
	initialKnowledge?: KnowledgeResponse;
	isEditMode: boolean;
	setIsEditMode: (v: boolean) => void;
	headerNode?: React.ReactNode;
	preHeaderNode?: React.ReactNode;
	onDeleteSuccess?: (deletedId: string) => void;
}

export const BatchKnowledgeTabContent = forwardRef<BatchTabHandle, BatchKnowledgeTabContentProps>(
	(
		{
			knowledgeId,
			initialKnowledge,
			isEditMode,
			setIsEditMode,
			headerNode,
			preHeaderNode,
			onDeleteSuccess,
		},
		ref,
	) => {
		const { data, isLoading, error } = useKnowledgeDetail(knowledgeId);
		const editKnowledge = useEditKnowledge();
		const deleteMutation = useDeleteKnowledge();
		const router = useRouter();

		const doc = data || initialKnowledge;

		const initialCategories = extractKnowledgeCategories(doc);
		const initialVisibility = (doc?.metadata?.visibility_settings as VisibilitySettings) || {
			clinics: ["all"],
			doctor_types: ["all"],
			doctors: ["all"],
		};
		const initialChunks = (doc?.metadata?.chunks as KnowledgeChunkItem[]) || [];

		const [pendingCategories, setPendingCategories] = useState<string[]>(initialCategories);
		const [pendingVisibilitySettings, setPendingVisibilitySettings] =
			useState<VisibilitySettings>(initialVisibility);
		const [pendingTitle, setPendingTitle] = useState(doc?.title || "");
		const [pendingSummary, setPendingSummary] = useState(doc?.ai_summary || "");
		const [pendingChunks, setPendingChunks] = useState<KnowledgeChunkItem[]>(initialChunks);
		const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
		const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);

		useEffect(() => {
			if (doc && !isEditMode) {
				const timer = setTimeout(() => {
					setPendingCategories(extractKnowledgeCategories(doc));
					setPendingVisibilitySettings(
						(doc.metadata?.visibility_settings as VisibilitySettings) || {
							clinics: ["all"],
							doctor_types: ["all"],
							doctors: ["all"],
						},
					);
					setPendingTitle(doc.title || "");
					setPendingSummary(doc.ai_summary || "");
					setPendingChunks((doc.metadata?.chunks as KnowledgeChunkItem[]) || []);
				}, 0);
				return () => clearTimeout(timer);
			}
		}, [doc, isEditMode]);

		const handleSave = async (newTitle?: string) => {
			await editKnowledge.mutateAsync({
				id: knowledgeId,
				data: {
					summary: pendingSummary || doc?.ai_summary || "",
					categories: pendingCategories,
					visibility_settings: pendingVisibilitySettings,
					title: typeof newTitle === "string" ? newTitle : pendingTitle,
					chunks: pendingChunks.length > 0 ? pendingChunks : undefined,
				},
			});
			setIsEditMode(false);
		};

		const handleDelete = async () => {
			await deleteMutation.mutateAsync(knowledgeId);
			toast.success("Knowledge deleted successfully");
			if (onDeleteSuccess) {
				onDeleteSuccess(knowledgeId);
			} else {
				router.push("/dashboard/knowledge");
			}
		};

		useImperativeHandle(ref, () => ({
			handleSave,
			handleCancel,
			triggerSave: () => {
				setIsSaveModalOpen(true);
			},
			handleDelete: async () => {
				setIsDeleteModalOpen(true);
			},
		}));

		if (error && !doc) {
			return (
				<div className="flex items-center justify-center h-full text-red-500">
					Error loading document details
				</div>
			);
		}

		const handleCancel = () => {
			setPendingCategories(initialCategories);
			setPendingVisibilitySettings(initialVisibility);
			setPendingTitle(doc?.title || "");
			setPendingSummary(doc?.ai_summary || "");
			setPendingChunks(initialChunks);
			setIsEditMode(false);
		};

		return (
			<div className="flex flex-col h-full bg-white relative">
				{/* Main Content Area */}
				<div className="flex flex-1 overflow-hidden">
					{/* Left Column (Chat / Preview) */}
					<ChatPreview
						mode="knowledge"
						knowledgeId={knowledgeId}
						knowledge={doc}
						knowledgeStatus={doc?.status}
						aiSummary={pendingSummary || doc?.ai_summary}
						summaryValue={pendingSummary}
						onChangeSummary={setPendingSummary}
						fileName={doc?.file_name}
						initialPrompt={(doc?.metadata?.initial_prompt as string) || undefined}
						files={(doc?.metadata?.files as { file_name: string; summary: string }[]) || []}
						isDetailLoading={isLoading && !doc}
						isEditMode={isEditMode}
						categories={pendingCategories}
						onChangeCategories={setPendingCategories}
						chunks={pendingChunks}
						onChangeChunks={setPendingChunks}
						visibilitySettings={pendingVisibilitySettings}
						onChangeVisibilitySettings={setPendingVisibilitySettings}
						title={pendingTitle}
						onChangeTitle={setPendingTitle}
						onSave={() => setIsSaveModalOpen(true)}
						headerNode={headerNode}
						preHeaderNode={preHeaderNode}
					/>
				</div>

				{/* Save Confirmation Modal */}
				<ConfirmationModal
					isOpen={isSaveModalOpen}
					onOpenChange={setIsSaveModalOpen}
					title="Save Knowledge?"
					description="Are you sure you want to save the changes of the knowledge? If you confirm, it will be implemented into the chatbot."
					confirmText="Save Knowledge"
					cancelText="Cancel"
					isLoading={editKnowledge.isPending}
					onConfirm={async () => {
						await handleSave();
						setIsSaveModalOpen(false);
					}}
				/>

				{/* Delete Confirmation Modal */}
				<ConfirmationModal
					isOpen={isDeleteModalOpen}
					onOpenChange={setIsDeleteModalOpen}
					title="Delete Knowledge?"
					description="Are you certain you want to delete this knowledge? If you proceed, it will be removed from the chatbot."
					confirmText="Delete Knowledge"
					cancelText="Cancel"
					variant="destructive"
					isLoading={deleteMutation.isPending}
					onConfirm={handleDelete}
				/>
			</div>
		);
	},
);
BatchKnowledgeTabContent.displayName = "BatchKnowledgeTabContent";
