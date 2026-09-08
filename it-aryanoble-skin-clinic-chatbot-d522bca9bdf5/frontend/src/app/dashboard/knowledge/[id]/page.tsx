"use client";

import { ChatPreview } from "@/components/shared/knowledge/ChatPreview";
import { ClassificationSidebar } from "@/components/shared/knowledge/ClassificationSidebar";
import { Button } from "@/components/ui/button";
import { RiArrowLeftLine, RiDeleteBin7Line, RiEdit2Line, RiCheckLine } from "@remixicon/react";
import { toast } from "sonner";

import { useRouter } from "next/navigation";
import { use, useState } from "react";
import { useDeleteKnowledge, useUpdateKnowledge, useKnowledgeDetail } from "../hooks/use-knowledge";
import { useSession } from "@/hooks/use-session";

export default function KnowledgeDetailPage({ params }: { params: Promise<{ id: string }> }) {
	const router = useRouter();
	const unwrappedParams = use(params);
	const id = unwrappedParams.id;
	const { data, isLoading, error } = useKnowledgeDetail(id);
	const deleteMutation = useDeleteKnowledge();
	const updateMutation = useUpdateKnowledge();
	const { user } = useSession();
	const hasWriteAccess = user?.accesses?.includes("knowledge:write");
	const hasDeleteAccess = user?.accesses?.includes("knowledge:delete");
	const [isEditMode, setIsEditMode] = useState(false);
	const [titleInput, setTitleInput] = useState<string>("");

	const handleDelete = () => {
		if (confirm("Are you sure you want to delete this knowledge document?")) {
			deleteMutation.mutate(id, {
				onSuccess: () => {
					router.push("/dashboard/knowledge");
				},
			});
		}
	};

	if (error) {
		return (
			<div className="flex items-center justify-center h-full text-red-500">
				Error loading document details
			</div>
		);
	}

	const formatDisplayTitle = (raw: string | undefined) => {
		if (!raw) return "Knowledge Document";
		return raw
			.replace(/\.[^/.]+$/, "") // strip extension
			.replace(/[_-]/g, " ") // replace underscores/dashes with spaces
			.replace(/\b\w/g, (c) => c.toUpperCase()); // title case
	};

	const handleToggleEdit = () => {
		if (isEditMode) {
			if (titleInput.trim() && titleInput !== data?.title) {
				updateMutation.mutate({
					id,
					data: { title: titleInput.trim() },
				});
			}
			setIsEditMode(false);
		} else {
			setTitleInput(data?.title || "");
			setIsEditMode(true);
		}
	};

	return (
		<div className="flex flex-col absolute inset-0">
			{/* Title Header with Actions */}
			<div className="flex items-center gap-4 p-4 border-b border-gray-200 shrink-0 bg-white justify-between">
				<div className="flex items-center gap-4">
					<Button variant="ghost" size="icon" onClick={() => router.back()} className="text-gray-500 hover:text-gray-900">
						<RiArrowLeftLine className="size-5" />
					</Button>
					<div>
						{isEditMode ? (
							<input
								type="text"
								value={titleInput}
								onChange={(e) => setTitleInput(e.target.value)}
								className="text-base font-semibold text-gray-900 border border-blue-300 rounded px-2 py-0.5 outline-none focus:ring-1 focus:ring-blue-500"
								placeholder="Document title"
							/>
						) : (
							<h1 className="text-lg font-semibold text-gray-900">{formatDisplayTitle(data?.title)}</h1>
						)}
						<p className="text-sm text-gray-500">Knowledge Document Details</p>
					</div>
				</div>

				<div className="flex items-center gap-2">
					{hasDeleteAccess && (
						<Button
							onClick={handleDelete}
							disabled={deleteMutation.isPending || isLoading}
							variant="outline"
							className="gap-2 text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
						>
							<RiDeleteBin7Line className="size-4" />
							Delete Knowledge
						</Button>
					)}
					{hasWriteAccess && (
						<Button
							variant={isEditMode ? "default" : "outline"}
							className={`gap-2 ${isEditMode ? "bg-emerald-600 hover:bg-emerald-700 text-white" : "text-zinc-950"}`}
							disabled={isLoading || updateMutation.isPending}
							onClick={handleToggleEdit}
						>
							{isEditMode ? <RiCheckLine className="size-4" /> : <RiEdit2Line className="size-4" />}
							{isEditMode ? "Save Changes" : "Edit Knowledge"}
						</Button>
					)}

				</div>
			</div>

			{/* Main Content Area */}
			<div className="flex flex-1 overflow-hidden">
				{/* Left Column (Chat / Preview) */}
				<ChatPreview
					knowledgeId={id}
					knowledgeStatus={data?.status}
					aiSummary={data?.ai_summary}
					fileName={formatDisplayTitle(data?.title || data?.file_name)}
					isDetailLoading={isLoading}
					isEditMode={isEditMode}
				/>

				{/* Right Column (Classification) */}
				<ClassificationSidebar knowledge={data} />
			</div>
		</div>
	);
}
