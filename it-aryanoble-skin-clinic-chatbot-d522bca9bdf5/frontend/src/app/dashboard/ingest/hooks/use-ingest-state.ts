import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
	useCreateGeneralChatSession,
	useIngestTextKnowledge,
	useIngestionQuota,
	useUploadKnowledge,
} from "../../knowledge/hooks/use-knowledge";
import { useProjects } from "../../knowledge/hooks/use-projects";
import { toast } from "sonner";

export function useIngestState() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const projectId = searchParams.get("projectId") || searchParams.get("project_id");

	const { data: projects = [] } = useProjects();
	const uploadMutation = useUploadKnowledge();
	const textIngestMutation = useIngestTextKnowledge();
	const { data: quota } = useIngestionQuota();

	const [uploadProgress, setUploadProgress] = useState<number>(0);
	const isProcessing = uploadMutation.isPending || textIngestMutation.isPending;

	const [mode, setMode] = useState<"ingest" | "general">("ingest");
	const [selectedProjectId, setSelectedProjectId] = useState<string>(projectId || "none");
	const [errorMsg, setErrorMsg] = useState<string | null>(null);
	const [promptValue, setPromptValue] = useState("");

	useEffect(() => {
		const timer = setTimeout(() => {
			if (projectId && projects.length > 0) {
				const exists = projects.some((p) => p.id === projectId);
				setSelectedProjectId(exists ? projectId : "none");
			}
		}, 0);
		return () => clearTimeout(timer);
	}, [projectId, projects]);

	const isGeneralMode = mode === "general";

	const selectedProjectName = useMemo(() => {
		if (!selectedProjectId || selectedProjectId === "none") {
			return "No Project";
		}
		const found = projects.find((p) => p.id === selectedProjectId);
		return found ? found.name : "Select Project";
	}, [selectedProjectId, projects]);

	const createGeneralSession = useCreateGeneralChatSession();

	const handleSend = (value: string, _category: string | undefined, files: File[]) => {
		setErrorMsg(null);

		if (isGeneralMode) {
			if (!value || !value.trim()) {
				setErrorMsg("Please enter a question or instruction for the Knowledge Base Assistant.");
				return false;
			}

			void (async () => {
				try {
					const session = await createGeneralSession.mutateAsync();
					router.push(
						`/dashboard/ingest/chat?session_id=${session.id}&q=${encodeURIComponent(value.trim())}`,
					);
				} catch {
					router.push(`/dashboard/ingest/chat?q=${encodeURIComponent(value.trim())}`);
				}
			})();
			return;
		}

		const isValidProject =
			selectedProjectId !== "none" && projects.some((p) => p.id === selectedProjectId);
		const targetProject = isValidProject ? selectedProjectId : null;

		// 1. Files attached -> Standard Multipart Ingestion Flow
		if (files.length > 0) {
			const MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024; // 500 MB
			const oversizedFile = files.find((f) => f.size > MAX_FILE_SIZE_BYTES);
			if (oversizedFile) {
				const sizeMb = (oversizedFile.size / (1024 * 1024)).toFixed(1);
				toast.error(`File '${oversizedFile.name}' (${sizeMb} MB) melebihi batas maksimal upload 500 MB.`);
				return false;
			}

			const formData = new FormData();
			if (value && value.trim()) {
				formData.append("prompt", value.trim());
			}
			formData.append("replace_existing", "true");

			if (targetProject) {
				formData.append("project_id", targetProject);
			}

			files.forEach((file) => {
				formData.append("file", file);
			});

			setUploadProgress(0);
			uploadMutation.mutate(
				{
					formData,
					onProgress: (percent) => setUploadProgress(percent),
				},
				{
					onSuccess: (data: {
						batch_id?: string;
						upload_batch_id?: string;
						documents?: { knowledge_id: string }[];
					}) => {
						const batchId = (data.batch_id || data.upload_batch_id || "").trim();
						const kid = (data.documents?.[0]?.knowledge_id || "").trim();
						if (batchId) {
							router.push(`/dashboard/knowledge/batch/${batchId}`);
						} else if (kid) {
							router.push(`/dashboard/knowledge/${kid}`);
						} else if (targetProject) {
							router.push(`/dashboard/knowledge/project/${targetProject}`);
						} else {
							router.push("/dashboard/knowledge");
						}
					},
					onError: () => {
						setUploadProgress(0);
					},
				},
			);
			return;
		}

		// 2. No files attached -> Text-Only Ingestion Flow
		if (!value || !value.trim()) {
			setErrorMsg("Please provide knowledge text or attach files to ingest.");
			return false;
		}

		textIngestMutation.mutate(
			{
				text_content: value.trim(),
				project_id: targetProject,
			},
			{
				onSuccess: (data) => {
					const textKid = (data.knowledge_id || "").trim();
					if (textKid) {
						router.push(`/dashboard/knowledge/${textKid}`);
					} else if (targetProject) {
						router.push(`/dashboard/knowledge/project/${targetProject}`);
					} else {
						router.push("/dashboard/knowledge");
					}
				},
			},
		);
	};

	return {
		projectId,
		projects,
		quota,
		uploadProgress,
		isProcessing,
		mode,
		setMode,
		isGeneralMode,
		selectedProjectId,
		setSelectedProjectId,
		selectedProjectName,
		errorMsg,
		setErrorMsg,
		promptValue,
		setPromptValue,
		handleSend,
	};
}
