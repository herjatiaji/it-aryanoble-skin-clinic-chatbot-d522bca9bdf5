import { chatHistoryKeys } from "@/app/dashboard/chat-history/api/keys";
import { api } from "@/lib/axios";
import { getErrorMessage } from "@/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { categoryKeys } from "@/app/dashboard/category/api/keys";
import { knowledgeKeys, projectKeys } from "../api/keys";
import type {
	KnowledgeResponse,
	KnowledgeStatus,
	KnowledgeTextIngestRequest,
	KnowledgeTextIngestResponse,
	KnowledgeEditRequest,
	VisibilitySettings,
	QualityGateResponse,
	UpdateEvidencePayload,
	RegenerateSummaryResponse,
} from "../api/types";

export const invalidateAllKnowledgeQueries = (
	queryClient: ReturnType<typeof useQueryClient>,
	options?: {
		knowledgeId?: string | null;
		knowledgeIds?: string[] | null;
		batchId?: string | null;
		sessionId?: string | null;
	},
) => {
	queryClient.invalidateQueries({ queryKey: knowledgeKeys.all, refetchType: "all" });
	queryClient.invalidateQueries({ queryKey: projectKeys.all, refetchType: "all" });
	queryClient.invalidateQueries({ queryKey: categoryKeys.all, refetchType: "all" });
	queryClient.invalidateQueries({ queryKey: ["knowledge-batch"], refetchType: "all" });
	queryClient.invalidateQueries({ queryKey: ["knowledge-ingestion-quota"], refetchType: "all" });

	if (options?.knowledgeId) {
		queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(options.knowledgeId), refetchType: "all" });
		queryClient.invalidateQueries({ queryKey: knowledgeKeys.qualityGate(options.knowledgeId), refetchType: "all" });
	}
	if (Array.isArray(options?.knowledgeIds)) {
		options.knowledgeIds.forEach((kid) => {
			if (kid) {
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(kid), refetchType: "all" });
			}
		});
	}
	if (options?.batchId) {
		queryClient.invalidateQueries({ queryKey: ["knowledge-batch", options.batchId], refetchType: "all" });
	}
	if (options?.sessionId) {
		queryClient.invalidateQueries({ queryKey: ["general-session", options.sessionId], refetchType: "all" });
		queryClient.invalidateQueries({ queryKey: chatHistoryKeys.detail(options.sessionId), refetchType: "all" });
		queryClient.invalidateQueries({ queryKey: ["chat-messages", options.sessionId], refetchType: "all" });
		queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all, refetchType: "all" });
	}
};

/**
 * @param projectId project UUID, "none" for root-level documents only (not assigned to any project),
 *                  or undefined/"all" for every document across projects.
 */
export const useKnowledgeBaseList = (projectId?: string | null) => {
	const effectiveProjectId = projectId || "all";
	const queryKey = knowledgeKeys.list({ projectId: effectiveProjectId });
	return useQuery({
		queryKey,
		queryFn: async (): Promise<KnowledgeResponse[]> => {
			const response = await api.get("/knowledge/", { params: { project_id: effectiveProjectId } });
			return response.data;
		},
		refetchInterval: (query) => {
			const data = query.state.data;
			if (data?.some((item) => item.status === "PROCESSING")) {
				return 4000;
			}
			return false;
		},
	});
};

export const useKnowledgeDetail = (id: string) => {
	return useQuery({
		queryKey: knowledgeKeys.detail(id),
		queryFn: async (): Promise<KnowledgeResponse> => {
			const response = await api.get(`/knowledge/${id}`);
			return response.data;
		},
		enabled: !!id,
		// A deleted document answers 404: show it at once instead of retrying a request that cannot succeed
		retry: (failureCount, error) =>
			(error as { response?: { status?: number } })?.response?.status !== 404 && failureCount < 3,
		refetchInterval: (query) => {
			const data = query.state.data;
			if (data?.status === "PROCESSING") {
				return 3500;
			}
			// If newly PENDING but summary or accuracy is still settling from background task, continue polling
			const meta = data?.metadata as Record<string, unknown> | undefined;
			const hasAccuracy =
				(data?.ai_confidence !== null && data?.ai_confidence !== undefined && Number(data.ai_confidence) > 0) ||
				meta?.text_accuracy !== undefined ||
				meta?.ai_confidence !== undefined ||
				meta?.confidence_score !== undefined;
			if (data?.status === "PENDING" && (!data?.ai_summary || !hasAccuracy)) {
				return 3500;
			}
			return false;
		},
	});
};

export const useKnowledgeBatch = (batchId: string) => {
	return useQuery({
		queryKey: ["knowledge-batch", batchId],
		queryFn: async (): Promise<KnowledgeResponse[]> => {
			const response = await api.get(`/knowledge/batch/${batchId}`);
			return response.data;
		},
		enabled: !!batchId,
		refetchInterval: (query) => {
			const data = query.state.data;
			// 1. If data is not yet loaded or empty, poll with reasonable interval
			if (!data || data.length === 0) {
				return 3500;
			}

			// 2. If any document is still PROCESSING or in PARSING state
			const isAnyProcessing = data.some(
				(item) => item.status === "PROCESSING" || (item.metadata as Record<string, unknown>)?.status === "PARSING",
			);
			if (isAnyProcessing) {
				return 3500;
			}

			// 3. If batch only has 1 document so far, continue polling because
			// subsequent documents in the multi-file batch might still be extracting in the background
			if (data.length === 1) {
				return 3500;
			}

			// 4. If multi-document batch (>= 2) and any non-rejected doc is missing batch_summary,
			// continue polling to allow the background/coordinator summary synthesis to complete and update
			const hasMissingSummary = data.some(
				(item) => item.status !== "REJECTED" && !(item.metadata as Record<string, unknown>)?.batch_summary,
			);
			if (data.length >= 2 && hasMissingSummary) {
				return 3500;
			}

			return false;
		},
	});
};

// 800 KB chunks (0.78 MB) to strictly comply with corporate 3-layer restrictions (Layer 1: 1 MB limit, Layer 2 & 3: 5 MB limits)
const CHUNK_SIZE_BYTES = 800 * 1024;

async function uploadFilesWithAutoChunking(
	data: FormData,
	progressCb?: (percent: number) => void,
) {
	const files = data.getAll("file") as File[];
	const prompt = (data.get("prompt") as string) || "";
	const replaceExisting = data.get("replace_existing") !== "false";
	const projectId = (data.get("project_id") as string) || undefined;
	const existingBatchId = (data.get("batch_id") as string) || undefined;

	// Check if any file exceeds 4 MB threshold
	const hasLargeFile = files.some(
		(f) => f && typeof f.size === "number" && f.size > CHUNK_SIZE_BYTES,
	);

	// If single small file (<= 4 MB), perform fast standard upload
	if (!hasLargeFile && files.length <= 1) {
		const response = await api.post("/knowledge/upload", data, {
			onUploadProgress: (progressEvent) => {
				if (progressEvent.total && progressCb) {
					const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
					progressCb(percent);
				}
			},
		});
		return response.data;
	}

	// Multi-file or large file: process file-by-file with 800 KB chunk slicing (Layer 1 safe)
	const totalFiles = files.length;
	const sharedBatchId =
		existingBatchId ||
		(totalFiles > 1
			? typeof crypto !== "undefined" && crypto.randomUUID
				? crypto.randomUUID()
				: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
			: undefined);

	const allDocumentResponses: unknown[] = [];
	let lastResponseData: unknown = null;

	for (let fIdx = 0; fIdx < totalFiles; fIdx++) {
		const file = files[fIdx];
		if (!file) continue;

		if (file.size > CHUNK_SIZE_BYTES) {
			const totalChunks = Math.ceil(file.size / CHUNK_SIZE_BYTES);
			const uploadId =
				typeof crypto !== "undefined" && crypto.randomUUID
					? crypto.randomUUID()
					: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

			for (let i = 0; i < totalChunks; i++) {
				const start = i * CHUNK_SIZE_BYTES;
				const end = Math.min(file.size, start + CHUNK_SIZE_BYTES);
				const chunkBlob = file.slice(start, end, file.type || "application/octet-stream");
				const chunkForm = new FormData();
				chunkForm.append("upload_id", uploadId);
				chunkForm.append("chunk_index", i.toString());
				chunkForm.append("total_chunks", totalChunks.toString());
				chunkForm.append("filename", file.name);
				chunkForm.append("chunk", chunkBlob, file.name);

				await api.post("/knowledge/upload/chunk", chunkForm);

				if (progressCb) {
					const fileBasePercent = (fIdx / totalFiles) * 100;
					const chunkContribution = ((i + 1) / totalChunks) * (100 / totalFiles) * 0.95;
					progressCb(Math.min(95, Math.round(fileBasePercent + chunkContribution)));
				}
			}

			// All slices uploaded, complete and trigger ingestion pipeline
			const completeForm = new FormData();
			completeForm.append("upload_id", uploadId);
			completeForm.append("filename", file.name);
			completeForm.append("total_chunks", totalChunks.toString());
			if (prompt) completeForm.append("prompt", prompt);
			if (projectId) completeForm.append("project_id", projectId);
			if (sharedBatchId) completeForm.append("batch_id", sharedBatchId);
			completeForm.append("replace_existing", replaceExisting ? "true" : "false");

			const compRes = await api.post("/knowledge/upload/complete", completeForm);
			lastResponseData = compRes.data;
			const rData = compRes.data as { documents?: unknown[]; knowledge_id?: string } | undefined;
			if (rData?.documents) {
				allDocumentResponses.push(...rData.documents);
			} else if (rData?.knowledge_id) {
				allDocumentResponses.push(rData);
			}
		} else {
			// Single small file slice <= 4 MB
			const singleForm = new FormData();
			singleForm.append("file", file);
			if (prompt) singleForm.append("prompt", prompt);
			if (projectId) singleForm.append("project_id", projectId);
			if (sharedBatchId) singleForm.append("batch_id", sharedBatchId);
			singleForm.append("replace_existing", replaceExisting ? "true" : "false");

			const resp = await api.post("/knowledge/upload", singleForm);
			lastResponseData = resp.data;
			const rData = resp.data as { documents?: unknown[]; knowledge_id?: string } | undefined;
			if (rData?.documents) {
				allDocumentResponses.push(...rData.documents);
			} else if (rData?.knowledge_id) {
				allDocumentResponses.push(rData);
			}
		}

		if (progressCb) {
			progressCb(Math.round(((fIdx + 1) / totalFiles) * 100));
		}
	}

	if (totalFiles > 1 && sharedBatchId) {
		return {
			status: "success",
			batch_id: sharedBatchId,
			upload_batch_id: sharedBatchId,
			total_files: totalFiles,
			documents: allDocumentResponses,
			message: `Processed ${totalFiles} documents in batch.`,
		};
	}

	return lastResponseData;
}

export const useUploadKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (
			params:
				| FormData
				| {
						formData: FormData;
						onProgress?: (percent: number) => void;
				  },
		) => {
			const data = params instanceof FormData ? params : params.formData;
			const progressCb = params instanceof FormData ? undefined : params.onProgress;

			return await uploadFilesWithAutoChunking(data, progressCb);
		},
		onSuccess: () => {
			toast.success("Files uploaded successfully!");
			invalidateAllKnowledgeQueries(queryClient);
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to upload knowledge files."));
		},
	});
};

export const useReplaceKnowledgeFile = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			knowledgeId,
			formData,
			onProgress,
		}: {
			knowledgeId: string;
			formData: FormData;
			onProgress?: (percent: number) => void;
		}) => {
			const file = formData.get("file") as File | null;
			const prompt = (formData.get("prompt") as string) || "";

			// If file exceeds 800 KB, slice and upload via chunked pipeline (Layer 1 safe)
			if (file && typeof file.size === "number" && file.size > CHUNK_SIZE_BYTES) {
				const totalChunks = Math.ceil(file.size / CHUNK_SIZE_BYTES);
				const uploadId =
					typeof crypto !== "undefined" && crypto.randomUUID
						? crypto.randomUUID()
						: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

				for (let i = 0; i < totalChunks; i++) {
					const start = i * CHUNK_SIZE_BYTES;
					const end = Math.min(file.size, start + CHUNK_SIZE_BYTES);
					const chunkBlob = file.slice(start, end);
					const chunkForm = new FormData();
					chunkForm.append("upload_id", uploadId);
					chunkForm.append("chunk_index", i.toString());
					chunkForm.append("total_chunks", totalChunks.toString());
					chunkForm.append("filename", file.name);
					chunkForm.append("chunk", chunkBlob, file.name);

					await api.post("/knowledge/upload/chunk", chunkForm);

					if (onProgress) {
						const percent = Math.min(95, Math.round(((i + 1) / (totalChunks + 0.5)) * 100));
						onProgress(percent);
					}
				}

				const completeForm = new FormData();
				completeForm.append("upload_id", uploadId);
				completeForm.append("filename", file.name);
				completeForm.append("total_chunks", totalChunks.toString());
				if (prompt) completeForm.append("prompt", prompt);

				const compRes = await api.post(`/knowledge/${knowledgeId}/replace-file/complete`, completeForm);
				if (onProgress) onProgress(100);
				return compRes.data;
			}

			const response = await api.post(`/knowledge/${knowledgeId}/replace-file`, formData, {
				onUploadProgress: (progressEvent) => {
					if (progressEvent.total && onProgress) {
						const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
						onProgress(percent);
					}
				},
			});
			return response.data;
		},
		onSuccess: (_, variables) => {
			toast.success("File replaced! Ingestion re-processing in background.");
			invalidateAllKnowledgeQueries(queryClient, { knowledgeId: variables.knowledgeId });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to replace file."));
		},
	});
};

export const useIngestTextKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (
			payload: KnowledgeTextIngestRequest,
		): Promise<KnowledgeTextIngestResponse> => {
			const response = await api.post("/knowledge/text", payload);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Knowledge text ingestion initiated!");
			invalidateAllKnowledgeQueries(queryClient);
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to ingest knowledge text."));
		},
	});
};

export const useUpdateKnowledgeStatus = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id, status }: { id: string; status: KnowledgeStatus }) => {
			const response = await api.patch(`/knowledge/${id}/status`, { status });
			return response.data;
		},
		onSuccess: (_, variables) => {
			toast.success("Status updated successfully!");
			invalidateAllKnowledgeQueries(queryClient, { knowledgeId: variables?.id });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to update status."));
		},
	});
};

// A save or approval whose connection is cut before the server answers (proxy timeout, network drop) may still
// complete on the server: the browser then only sees a network/CORS error with no response.
export const connectionLost = (error: unknown) => {
	const err = error as { response?: unknown; code?: string; message?: string } | undefined;
	return !!err && !err.response && (err.code === "ERR_NETWORK" || err.code === "ECONNABORTED" || err.message === "Network Error");
};

const CONNECTION_LOST_MESSAGE =
	"The connection to the server was lost before saving finished. The changes may have been saved; the document has been reloaded to show its current state.";

export const useApproveKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (id: string) => {
			const response = await api.post(`/knowledge/${id}/approve`);
			return response.data;
		},
		onSuccess: (data, id) => {
			if (data?.status === "partial") {
				// Approved, but the chatbot index still serves the previous version
				toast.warning(data.message || "Document approved, but it could not be published to the AI Knowledge Base.");
			} else {
				toast.success("Document approved and indexed into AI Knowledge Base!");
			}
			invalidateAllKnowledgeQueries(queryClient, { knowledgeId: id });
		},
		onError: (error: unknown, id) => {
			if (connectionLost(error)) {
				toast.warning(CONNECTION_LOST_MESSAGE);
				invalidateAllKnowledgeQueries(queryClient, { knowledgeId: id });
				return;
			}
			toast.error(getErrorMessage(error, "Failed to approve and index document."));
		},
	});
};

export const useReparseVisionKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id, pageNumbers }: { id: string; pageNumbers?: number[] }) => {
			const response = await api.post(`/knowledge/${id}/reparse_vision`, {
				page_numbers: pageNumbers,
				max_pages: 1000,
			});
			return response.data;
		},
		onSuccess: (_, { id }) => {
			toast.success("Dokumen berhasil di-reparse dengan Vision LLM!");
			invalidateAllKnowledgeQueries(queryClient, { knowledgeId: id });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Gagal memproses ulang dokumen dengan Vision."));
		},
	});
};

export const useApproveBatchKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (batchId: string) => {
			const response = await api.post(`/knowledge/batch/${batchId}/approve`);
			return response.data;
		},
		onSuccess: (_, batchId) => {
			toast.success("All documents approved and indexed into AI Knowledge Base!");
			invalidateAllKnowledgeQueries(queryClient, { batchId });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to approve batch documents."));
		},
	});
};

export const useUpdateBatchVisibility = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			batchId,
			visibilitySettings,
		}: {
			batchId: string;
			visibilitySettings: VisibilitySettings;
		}) => {
			const response = await api.put(`/knowledge/batch/${batchId}/visibility`, {
				visibility_settings: visibilitySettings,
			});
			return response.data;
		},
		onSuccess: (_, variables) => {
			toast.success("Batch visibility settings updated successfully!");
			invalidateAllKnowledgeQueries(queryClient, { batchId: variables.batchId });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to update batch visibility settings."));
		},
	});
};

export const useDeleteKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (param: string | { id: string; hideToast?: boolean }) => {
			const id = typeof param === "string" ? param : param.id;
			const hideToast = typeof param === "string" ? false : !!param.hideToast;
			const response = await api.delete(`/knowledge/${id}`);
			return { data: response.data, hideToast, id };
		},
		onSuccess: (result, variables) => {
			if (!result?.hideToast) {
				toast.success("Knowledge deleted successfully!");
			}
			const id = typeof variables === "string" ? variables : variables.id;
			queryClient.removeQueries({ queryKey: knowledgeKeys.detail(id) });
			invalidateAllKnowledgeQueries(queryClient, { knowledgeId: id });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to delete knowledge document."));
		},
	});
};

export const useEditKnowledge = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			id,
			data,
			hideToast,
		}: {
			id: string;
			data: KnowledgeEditRequest;
			hideToast?: boolean;
		}) => {
			const response = await api.put(`/knowledge/${id}`, data);
			return { data: response.data, hideToast, id };
		},
		onSuccess: (result, variables) => {
			if (!result.hideToast) {
				toast.success("Document updated successfully!");
			}
			invalidateAllKnowledgeQueries(queryClient, { knowledgeId: variables.id });
		},
		onError: (error: unknown, variables) => {
			if (connectionLost(error)) {
				toast.warning(CONNECTION_LOST_MESSAGE);
				invalidateAllKnowledgeQueries(queryClient, { knowledgeId: variables.id });
				return;
			}
			toast.error(getErrorMessage(error, "Failed to update document."));
		},
	});
};


export const useIngestionQuota = () => {
	return useQuery({
		queryKey: ["knowledge-ingestion-quota"],
		queryFn: async (): Promise<{
			year_month: string;
			tokens_used: number;
			input_tokens: number;
			output_tokens: number;
			token_limit: number;
			percentage: number;
			documents_count: number;
			warning: boolean;
			exceeded: boolean;
		}> => {
			const response = await api.get("/knowledge/quota");
			return response.data;
		},
	});
};

export const useUpdateKnowledgeProject = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			knowledgeId,
			projectId,
			hideToast,
		}: {
			knowledgeId: string;
			projectId: string | null;
			hideToast?: boolean;
		}) => {
			const response = await api.put(`/knowledge/${knowledgeId}/project`, {
				project_id: projectId,
			});
			return { data: response.data, hideToast, knowledgeId };
		},
		onSuccess: (result, variables) => {
			if (!result?.hideToast) {
				toast.success("Knowledge project updated successfully!");
			}
			// Optimistically remove from root list if assigned to a project
			const filterOutOrUpdate = (oldData?: KnowledgeResponse[]) => {
				// knowledgeKeys.all also matches detail and paginated queries, whose data is not a list
				if (!Array.isArray(oldData)) return oldData;
				if (variables.projectId && variables.projectId !== "none") {
					return oldData.filter((item) => item.id !== variables.knowledgeId);
				}
				return oldData.map((item) => {
					if (item.id === variables.knowledgeId) {
						return {
							...item,
							project_id: variables.projectId,
							metadata: {
								...(item.metadata || {}),
								project_id: variables.projectId,
							},
						};
					}
					return item;
				});
			};
			queryClient.setQueriesData<KnowledgeResponse[]>(
				{ queryKey: knowledgeKeys.list({ projectId: "none" }) },
				filterOutOrUpdate,
			);
			queryClient.setQueriesData<KnowledgeResponse[]>(
				{ queryKey: knowledgeKeys.all },
				filterOutOrUpdate,
			);
			invalidateAllKnowledgeQueries(queryClient, { knowledgeId: variables?.knowledgeId });
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to update project assignment."));
		},
	});
};

export interface QueryGeneralPayload {
	prompt: string;
	history?: Array<{ role: string; content: string }>;
}

export interface QueryGeneralResult {
	type?: "answer" | "confirmation" | "success" | "cancelled" | "error" | string;
	message?: string;
	operation_id?: string | null;
	prompt: string;
	answer: string;
	action: "read" | "edit_preview" | "delete_preview" | "edit_applied" | "delete_applied" | string;
	target_knowledge_id?: string | null;
	total_found: number;
	results: Array<Record<string, unknown>>;
}

export interface OperationResult {
	type: "success" | "cancelled" | "info" | "error" | string;
	action: string;
	operation_id?: string;
	target_item?: string;
	target_knowledge_id?: string;
	affected_knowledge_ids?: string[];
	batch_id?: string;
	message: string;
}

export const useConfirmOperation = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			operationId,
			sessionId,
		}: {
			operationId: string;
			sessionId?: string | null;
		}): Promise<OperationResult> => {
			const url = sessionId
				? `/knowledge/operations/${operationId}/confirm?session_id=${sessionId}`
				: `/knowledge/operations/${operationId}/confirm`;
			const response = await api.post(url);
			return response.data;
		},
		onSuccess: (data, variables) => {
			invalidateAllKnowledgeQueries(queryClient, {
				knowledgeId: data.target_knowledge_id,
				knowledgeIds: data.affected_knowledge_ids,
				batchId: data.batch_id,
				sessionId: variables.sessionId,
			});
			toast.success(data.message || "Operasi berhasil diterapkan!");
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Gagal mengonfirmasi operasi."));
		},
	});
};

export const useCancelOperation = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			operationId,
			sessionId,
		}: {
			operationId: string;
			sessionId?: string | null;
		}): Promise<OperationResult> => {
			const url = sessionId
				? `/knowledge/operations/${operationId}/cancel?session_id=${sessionId}`
				: `/knowledge/operations/${operationId}/cancel`;
			const response = await api.post(url);
			return response.data;
		},
		onSuccess: (data, variables) => {
			if (variables.sessionId) {
				queryClient.invalidateQueries({ queryKey: ["general-session", variables.sessionId], refetchType: "all" });
				queryClient.invalidateQueries({ queryKey: chatHistoryKeys.detail(variables.sessionId), refetchType: "all" });
				queryClient.invalidateQueries({ queryKey: ["chat-messages", variables.sessionId], refetchType: "all" });
				queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all, refetchType: "all" });
			}
			toast.info(data.message || "Operasi dibatalkan.");
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Gagal membatalkan operasi."));
		},
	});
};

export const useQueryGeneral = () => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (payload: QueryGeneralPayload): Promise<QueryGeneralResult> => {
			const response = await api.post("/knowledge/query-general", payload);
			return response.data;
		},
		onSuccess: (data) => {
			if (data.action === "edit_applied" || data.action === "delete_applied") {
				invalidateAllKnowledgeQueries(queryClient, {
					knowledgeId: data.target_knowledge_id,
				});
			}
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Failed to execute knowledge query."));
		},
	});
};

export interface GeneralChatMessageItem {
	id: string;
	role: string;
	content: string;
	action?: string | null;
	type?: string | null;
	operation_id?: string | null;
	target_knowledge_id?: string | null;
	total_found?: number | null;
	attachments?: Record<string, unknown> | null;
	created_at: string;
}

export interface GeneralChatSessionResponse {
	id: string;
	user_id: string;
	session_type: string;
	status: string;
	messages: GeneralChatMessageItem[];
	created_at: string;
	updated_at: string;
}

export const useGeneralChatSession = (sessionId?: string | null) => {
	return useQuery({
		queryKey: ["general-session", sessionId],
		queryFn: async (): Promise<GeneralChatSessionResponse> => {
			const response = await api.get(`/knowledge/general-session/${sessionId}`);
			return response.data;
		},
		enabled: !!sessionId,
	});
};

export const useCreateGeneralChatSession = () => {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async (): Promise<GeneralChatSessionResponse> => {
			const response = await api.post("/knowledge/general-session");
			return response.data;
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all, refetchType: "all" });
		},
	});
};

export const useSendGeneralChatMessage = (sessionId?: string | null) => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (payload: {
			prompt: string;
			attachments?: Record<string, unknown>;
			signal?: AbortSignal;
		}): Promise<GeneralChatSessionResponse> => {
			const { signal, ...body } = payload;
			const response = await api.post(`/knowledge/general-session/${sessionId}/messages`, body, {
				signal,
			});
			return response.data;
		},
		onSuccess: (data) => {
			queryClient.setQueryData(["general-session", sessionId], data);
			queryClient.invalidateQueries({ queryKey: chatHistoryKeys.all, refetchType: "all" });
			if (sessionId) {
				queryClient.invalidateQueries({ queryKey: chatHistoryKeys.detail(sessionId), refetchType: "all" });
				queryClient.invalidateQueries({ queryKey: ["chat-messages", sessionId], refetchType: "all" });
			}
			const latestMsg = data.messages[data.messages.length - 1];
			const isEditOrDeleteApplied =
				latestMsg?.action === "edit_applied" ||
				latestMsg?.action === "delete_applied" ||
				(latestMsg?.attachments as Record<string, unknown>)?.action === "edit_applied" ||
				(latestMsg?.attachments as Record<string, unknown>)?.action === "delete_applied";

			if (isEditOrDeleteApplied) {
				const targetKid =
					latestMsg.target_knowledge_id ||
					((latestMsg.attachments as Record<string, unknown>)?.target_knowledge_id as string);
				const affectedKids = (latestMsg.attachments as Record<string, unknown>)
					?.affected_knowledge_ids as string[] | undefined;

				invalidateAllKnowledgeQueries(queryClient, {
					knowledgeId: targetKid,
					knowledgeIds: affectedKids,
				});
			}
		},
		onError: (error: unknown) => {
			const isCanceled =
				(error as { name?: string; code?: string })?.name === "CanceledError" ||
				(error as { name?: string; code?: string })?.code === "ERR_CANCELED";
			if (!isCanceled) {
				toast.error(getErrorMessage(error, "Failed to send message."));
			}
		},
	});
};


// =============================================================================
// PHASE 1.5 QUALITY GATE & STAGING OBSERVABILITY HOOKS (D1-a & D9)
// =============================================================================

export const useQualityGate = (
	knowledgeId?: string | null,
	options?: { summaryOnly?: boolean; enabled?: boolean },
) => {
	const summaryOnly = options?.summaryOnly ?? false;
	const isEnabled = options?.enabled !== undefined ? options.enabled && !!knowledgeId : !!knowledgeId;

	return useQuery({
		queryKey: knowledgeId
			? [...knowledgeKeys.qualityGate(knowledgeId), { summaryOnly }]
			: ["knowledge-quality-gate-disabled"],
		queryFn: async (): Promise<QualityGateResponse> => {
			const response = await api.get(`/knowledge/${knowledgeId}/quality-gate`, {
				params: summaryOnly ? { summary_only: true } : undefined,
			});
			return response.data;
		},
		enabled: isEnabled,
		refetchInterval: (query) => {
			const data = query.state.data;
			if (data?.job_status === "PENDING" || data?.job_status === "PROCESSING") {
				return 3000;
			}
			return false;
		},
	});
};

export const useRunQualityCheck = (knowledgeId: string) => {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async () => {
			const response = await api.post(`/knowledge/${knowledgeId}/quality-check`);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Pemeriksaan kualitas dijadwalkan. Hasil muncul dalam 1-2 menit.");
			// The check runs in the background: refresh the gate when it is likely done
			setTimeout(() => {
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.qualityGate(knowledgeId) });
			}, 90000);
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Gagal menjadwalkan pemeriksaan kualitas."));
		},
	});
};

export const useUpdateEvidence = (knowledgeId?: string | null) => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({
			evidenceId,
			data,
		}: {
			evidenceId: string;
			data: UpdateEvidencePayload;
		}) => {
			const response = await api.put(`/knowledge/${knowledgeId}/evidence/${evidenceId}`, data);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Evidence berhasil diperbarui (SSOT Derivation: ADMIN_EDIT)");
			if (knowledgeId) {
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.qualityGate(knowledgeId), refetchType: "all" });
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(knowledgeId), refetchType: "all" });
			}
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Gagal memperbarui evidence"));
		},
	});
};

export const useResolveEvidence = (knowledgeId?: string | null) => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (evidenceId: string) => {
			const response = await api.post(`/knowledge/${knowledgeId}/evidence/${evidenceId}/resolve`);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Item visual berhasil disetujui (VISION_COMPLETE). Knowledge Readiness Gate diperbarui.");
			if (knowledgeId) {
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.qualityGate(knowledgeId), refetchType: "all" });
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(knowledgeId), refetchType: "all" });
			}
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Gagal menyelesaikan review evidence"));
		},
	});
};

export const useRegenerateSummary = (knowledgeId?: string | null) => {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (): Promise<RegenerateSummaryResponse> => {
			const response = await api.post(`/knowledge/${knowledgeId}/regenerate-summary`);
			return response.data;
		},
		onSuccess: () => {
			toast.success("Ringkasan berhasil diregenerasi dari Canonical Evidence SSOT.");
			if (knowledgeId) {
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(knowledgeId), refetchType: "all" });
				queryClient.invalidateQueries({ queryKey: knowledgeKeys.qualityGate(knowledgeId), refetchType: "all" });
			}
		},
		onError: (error: unknown) => {
			toast.error(getErrorMessage(error, "Gagal meregenerasi ringkasan dari evidence"));
		},
	});
};

