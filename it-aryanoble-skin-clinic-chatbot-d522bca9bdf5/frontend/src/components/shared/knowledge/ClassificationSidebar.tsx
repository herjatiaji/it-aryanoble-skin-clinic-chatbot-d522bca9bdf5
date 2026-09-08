import { KnowledgeResponse } from "@/app/dashboard/knowledge/api/types";
import { useUpdateKnowledgeStatus, useApproveKnowledge } from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { RiCheckLine, RiCloseLine, RiFilePdf2Line, RiMedicineBottleLine } from "@remixicon/react";
import { useSession } from "@/hooks/use-session";

interface ClassificationSidebarProps {
	knowledge?: KnowledgeResponse;
}

export function ClassificationSidebar({ knowledge }: ClassificationSidebarProps) {
	const updateStatus = useUpdateKnowledgeStatus();
	const approveKnowledge = useApproveKnowledge();
	const { user } = useSession();
	const hasWriteAccess = user?.accesses?.includes("knowledge:write");

	if (!knowledge) return null;

	const handleApprove = () => {
		approveKnowledge.mutate(knowledge.id);
		if (typeof window !== "undefined") {
			localStorage.removeItem(`chat_preview_${knowledge.id}`);
		}
	};

	const handleReject = () => {
		updateStatus.mutate({ id: knowledge.id, status: "REJECTED" });
	};

	return (
		<div className="w-70 lg:w-[320px] shrink-0 p-4 bg-zinc-50/50 border-l border-black/5 flex flex-col overflow-y-auto gap-4">
			<div className="bg-white rounded-md border border-black/10 shadow-sm flex flex-col overflow-hidden shrink-0">
				<div className="p-3 border-b border-black/5">
					<h2 className="text-sm font-medium text-zinc-950">Knowledge Classification</h2>
				</div>

				<div className="p-3.5 flex flex-col gap-4">
					{/* Title */}
					<div>
						<label className="text-xs font-medium text-zinc-500 mb-1 block">Title</label>
						<p className="text-sm text-zinc-950">
							{knowledge.title
								? knowledge.title
										.replace(/\.[^/.]+$/, "")
										.replace(/[_-]/g, " ")
										.replace(/\b\w/g, (c) => c.toUpperCase())
								: ""}
						</p>
					</div>

					{/* Type */}
					<div>
						<label className="text-xs font-medium text-zinc-500 mb-1 block">Type</label>
						<div className="flex items-center gap-1.5 text-blue-600">
							<RiMedicineBottleLine className="size-4" />
							<span className="text-sm font-medium">{knowledge.type}</span>
						</div>
					</div>

					{/* Source */}
					<div>
						<label className="text-xs font-medium text-zinc-500 mb-1 block">Source</label>
						<div className="flex items-center gap-1.5 text-red-500">
							<RiFilePdf2Line className="size-4" />
							<span className="text-sm font-medium">
								{knowledge.file_name?.split(".").pop()?.toUpperCase() || "FILE"}
							</span>
						</div>
					</div>

					<div>
						<label className="text-xs font-medium text-zinc-500 mb-1 block">Status</label>
						{knowledge.status === "APPROVED" && (
							<Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-50 font-medium">
								{knowledge.status}
							</Badge>
						)}
						{knowledge.status === "PENDING" && (
							<Badge className="bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-50 font-medium">
								{knowledge.status}
							</Badge>
						)}
						{knowledge.status === "PROCESSING" && (
							<Badge className="bg-blue-50 text-blue-700 border-blue-200 animate-pulse hover:bg-blue-50 font-medium">
								{knowledge.status}
							</Badge>
						)}
						{knowledge.status === "REJECTED" && (
							<Badge className="bg-red-50 text-red-700 border-red-200 hover:bg-red-50 font-medium">
								{knowledge.status}
							</Badge>
						)}
						{!["APPROVED", "PENDING", "PROCESSING", "REJECTED"].includes(knowledge.status) && (
							<Badge variant="secondary" className="font-medium">
								{knowledge.status}
							</Badge>
						)}
					</div>

					{/* AI Confidence Score */}
					<div className="pt-2">
						<label className="text-xs font-medium text-zinc-500 mb-2 block">
							AI Confidence Score
						</label>
						<div className="bg-blue-50/50 rounded-md p-2.5">
							<div className="flex justify-between items-center mb-1.5">
								<span className="text-xs text-zinc-950">Text Accuracy</span>
								<span className="text-xs font-medium text-blue-600">
									{knowledge.ai_confidence !== null && knowledge.ai_confidence !== undefined
										? `${Number(knowledge.ai_confidence)}%`
										: knowledge.status === "PROCESSING"
											? "Calculating..."
											: "—"}
								</span>
							</div>
							<Progress
								value={
									knowledge.ai_confidence !== null && knowledge.ai_confidence !== undefined
										? Number(knowledge.ai_confidence)
										: 0
								}
								className="h-2 bg-blue-100"
							/>
						</div>
					</div>
				</div>
			</div>

			{/* Manual Approval Action Card when status is PENDING or PROCESSING */}
			{knowledge.status === "PENDING" && hasWriteAccess && (
				<div className="bg-white rounded-md border border-amber-200 shadow-sm p-4 flex flex-col gap-3">
					<div className="flex flex-col">
						<h3 className="text-sm font-semibold text-zinc-900">Review & Approval</h3>
						<p className="text-xs text-zinc-500 mt-1">
							Review the AI summary and chat with the document. Once verified, click approve to
							activate this knowledge base.
						</p>
					</div>
					<div className="flex flex-col gap-2 pt-1">
						<Button
							onClick={handleApprove}
							disabled={approveKnowledge.isPending}
							className="w-full bg-emerald-600 hover:bg-emerald-700 text-white gap-2"
						>
							<RiCheckLine className="size-4" />
							Approve Knowledge
						</Button>
						<Button
							onClick={handleReject}
							disabled={updateStatus.isPending}
							variant="outline"
							className="w-full text-red-600 hover:text-red-700 border-red-200 hover:bg-red-50 gap-2"
						>
							<RiCloseLine className="size-4" />
							Reject Knowledge
						</Button>
					</div>
				</div>
			)}
		</div>
	);
}
