import {
	Attachment,
	AttachmentAction,
	AttachmentActions,
	AttachmentContent,
	AttachmentDescription,
	AttachmentMedia,
	AttachmentTitle,
} from "@/components/ui/attachment";
import { Button } from "@/components/ui/button";
import {
	MessageScroller,
	MessageScrollerContent,
	MessageScrollerItem,
	MessageScrollerProvider,
	MessageScrollerSmartButton,
	MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { api } from "@/lib/axios";
import {
	RiAlertLine,
	RiAttachment2,
	RiCheckboxCircleFill,
	RiCheckLine,
	RiCloseCircleLine,
	RiCloseLine,
	RiCornerDownLeftLine,
	RiDeleteBin7Line,
	RiEdit2Line,
	RiFileExcel2Line,
	RiFilePdf2Line,
	RiFilePpt2Line,
	RiFileTextLine,
	RiFileWord2Line,
	RiImage2Line,
	RiLoader4Line,
	RiRobot2Line,
	RiStopCircleLine,
	RiUploadCloud2Line,
	RiUser3Line,
} from "@remixicon/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import {
	VisibilitySettings as IVisibilitySettings,
	KnowledgeChunkItem,
	KnowledgeResponse,
} from "@/app/dashboard/knowledge/api/types";
import {
	invalidateAllKnowledgeQueries,
	useCancelOperation,
	useConfirmOperation,
	useGeneralChatSession,
	useReplaceKnowledgeFile,
	useSendGeneralChatMessage,
} from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { MarkdownContent } from "@/components/shared/markdown-content";
import { cleanDeletedItemFromMarkdown, cleanMessageTurn, resolveImageUrl } from "@/components/shared/markdown/utils";
import { StreamingMarkdown } from "@/components/shared/streaming-markdown";
import { WysiwygEditor } from "@/components/shared/wysiwyg-editor";
import { toast } from "sonner";
import { ApprovalActions } from "./approval-actions";
import { CategorySettings } from "./category-settings";
import { ProcessingPipelineCard } from "./processing-pipeline-card";
import { TitleSettings } from "./title-settings";
import { VisibilitySettings as VisibilitySettingsUI } from "./visibility-settings";

interface ChatPreviewProps {
	mode?: "knowledge" | "general";
	sessionId?: string | null;
	initialPrompt?: string;
	knowledgeId?: string;
	knowledge?: KnowledgeResponse;
	knowledgeStatus?: string;
	aiSummary?: string | null;
	summaryValue?: string;
	onChangeSummary?: (val: string) => void;
	fileName?: string | null;
	files?: { file_name: string; summary: string; [key: string]: unknown }[];
	isDetailLoading?: boolean;
	isEditMode?: boolean;
	categories?: string[];
	onChangeCategories?: (newCategories: string[]) => void;
	chunks?: KnowledgeChunkItem[];
	onChangeChunks?: (chunks: KnowledgeChunkItem[]) => void;
	visibilitySettings?: IVisibilitySettings;
	onChangeVisibilitySettings?: (settings: IVisibilitySettings) => void;
	title?: string;
	onChangeTitle?: (title: string) => void;
	onSave?: (newTitle?: string) => void;
	headerNode?: React.ReactNode;
	preHeaderNode?: React.ReactNode;
}

interface Message {
	role: "user" | "assistant";
	content: string;
	attachmentName?: string;
	attachmentNames?: string[];
	action?: string;
	type?: string;
	operation_id?: string | null;
	operation_status?: string | null;
	attachments?: Record<string, unknown>;
	target_knowledge_id?: string | null;
	target_item?: string;
	total_found?: number;
}

function getInitialMessages(
	knowledge: KnowledgeResponse | undefined,
	knowledgeStatus: string | undefined,
	isEditMode: boolean,
	aiSummary: string | null | undefined,
	fileName: string | null | undefined,
	initialPrompt: string | undefined,
	initialSummarySnapshot?: string,
): Message[] {
	const currentSummary = aiSummary || knowledge?.ai_summary;

	const isProcessing =
		knowledgeStatus?.toUpperCase() === "PROCESSING" ||
		knowledge?.status?.toUpperCase() === "PROCESSING";

	const meta = knowledge?.metadata as Record<string, unknown> | undefined;
	const effectivePrompt =
		(initialPrompt && initialPrompt.trim()) ||
		(typeof meta?.initial_prompt === "string" && meta.initial_prompt.trim()) ||
		undefined;
	const docFile = fileName || knowledge?.file_name || undefined;

	// While actively processing, NEVER render stale assistant bubbles or old history
	if (isProcessing) {
		if (effectivePrompt) {
			return [
				{
					role: "user",
					content: effectivePrompt,
					attachmentName: docFile,
				},
			];
		}
		return [];
	}

	const rawHistory =
		Array.isArray(meta?.edit_history) && meta.edit_history.length > 0
			? meta.edit_history
			: Array.isArray(meta?.history) && meta.history.length > 0
				? meta.history
				: Array.isArray(meta?.chat_history) && meta.chat_history.length > 0
					? meta.chat_history
					: undefined;

	const history = rawHistory as
		| Array<{
				role: "user" | "assistant";
				content: string;
				attachmentName?: string;
				attachmentNames?: string[];
		  }>
		| undefined;

	const initialSummary =
		currentSummary || (meta?.initial_summary as string) || initialSummarySnapshot || undefined;

	// Build Turn 0
	const turn0: Message[] = [];
	if (effectivePrompt) {
		turn0.push({
			role: "user",
			content: effectivePrompt,
			attachmentName: docFile,
		});
	}
	if (initialSummary) {
		turn0.push({
			role: "assistant",
			content: initialSummary,
		});
	}

	if (Array.isArray(history) && history.length > 0) {
		const mapTurn = (
			m: {
				role: "user" | "assistant";
				content: string;
				attachmentName?: string;
				attachmentNames?: string[];
			},
			idx: number,
		): Message => {
			if (m.role === "user") {
				const cleaned = cleanMessageTurn(m.content, m.attachmentName, m.attachmentNames);
				return {
					role: "user",
					content: cleaned.content,
					attachmentName: cleaned.attachmentName,
					attachmentNames: cleaned.attachmentNames,
				};
			}
			let content = m.content;
			if (idx > 0 && content && />\s*\*\*Ringkasan Perubahan:\*\*/i.test(content)) {
				const match = content.match(
					/(?:^|\n)>\s*\*\*Ringkasan Perubahan:\*\*[\s\S]*?(?=\n#{1,3}\s+|\n\*\*[^*]+\*\*|\Z)/i,
				);
				if (match) {
					content = match[0].replace(/^>\s*/gm, "").trim();
				}
			}
			return {
				role: "assistant",
				content: content,
				attachmentName: m.attachmentName,
				attachmentNames: m.attachmentNames,
			};
		};

		const startsWithTurn0 =
			(effectivePrompt && history[0]?.role === "user" && history[0]?.content === effectivePrompt) ||
			(!effectivePrompt && history[0]?.role === "assistant") ||
			(history.length >= 2 && history[0]?.role === "user" && history[1]?.role === "assistant");

		if (startsWithTurn0 || history[0]?.role === "user") {
			const mapped = history.map(mapTurn);
			if (currentSummary) {
				for (let i = mapped.length - 1; i >= 0; i--) {
					if (mapped[i].role === "assistant" && !mapped[i].content) {
						mapped[i].content = currentSummary;
						break;
					}
				}
			}
			return mapped;
		}

		const mapped = [...turn0, ...history.map(mapTurn)];
		if (currentSummary) {
			for (let i = mapped.length - 1; i >= 0; i--) {
				if (mapped[i].role === "assistant" && !mapped[i].content) {
					mapped[i].content = currentSummary;
					break;
				}
			}
		}
		return mapped;
	}

	if (initialSummary) {
		if (effectivePrompt) {
			return [
				{ role: "user", content: effectivePrompt, attachmentName: docFile },
				{ role: "assistant", content: initialSummary },
			];
		}
		return [{ role: "assistant", content: initialSummary }];
	}

	return [];
}

export function ChatPreview({
	mode = "knowledge",
	sessionId,
	initialPrompt,
	knowledgeId,
	knowledge,
	knowledgeStatus,
	aiSummary,
	summaryValue,
	onChangeSummary,
	fileName,
	files = [],
	isDetailLoading = false,
	isEditMode = false,
	categories = [],
	onChangeCategories,
	chunks = [],
	onChangeChunks,
	visibilitySettings,
	onChangeVisibilitySettings,
	title,
	onChangeTitle,
	headerNode,
	preHeaderNode,
}: ChatPreviewProps) {
	const { data: generalSession } = useGeneralChatSession(mode === "general" ? sessionId : null);
	const sendGeneralMsg = useSendGeneralChatMessage(mode === "general" ? sessionId : null);
	const confirmOp = useConfirmOperation();
	const cancelOp = useCancelOperation();
	const replaceFileMutation = useReplaceKnowledgeFile();
	const retryFileInputRef = useRef<HTMLInputElement>(null);
	const [isReplacingFile, setIsReplacingFile] = useState(false);
	const [activeOpId, setActiveOpId] = useState<string | null>(null);
	const [activeOpAction, setActiveOpAction] = useState<"confirm" | "cancel" | null>(null);
	const [completedOps, setCompletedOps] = useState<Record<string, "confirmed" | "cancelled">>({});
	const [isManualEditing, setIsManualEditing] = useState(false);
	const incomingSummary = summaryValue || aiSummary || knowledge?.ai_summary || "";
	const [prevIncomingSummary, setPrevIncomingSummary] = useState(incomingSummary);
	const [localSummary, setLocalSummary] = useState(incomingSummary);
	const [backupManualSummary, setBackupManualSummary] = useState<string>("");
	const [manualEditRevision, setManualEditRevision] = useState(0);

	const handleRetryFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
		const selectedFile = e.target.files?.[0];
		if (!selectedFile || !knowledgeId) return;

		const formData = new FormData();
		formData.append("file", selectedFile);
		if (initialPrompt) {
			formData.append("prompt", initialPrompt);
		}

		setIsReplacingFile(true);
		try {
			await replaceFileMutation.mutateAsync({
				knowledgeId,
				formData,
			});
		} catch {
			// handled in mutation
		} finally {
			setIsReplacingFile(false);
			if (e.target) e.target.value = "";
		}
	};

	if (incomingSummary !== prevIncomingSummary) {
		setPrevIncomingSummary(incomingSummary);
		if (!isManualEditing) {
			setLocalSummary(incomingSummary);
		}
	}

	const handleSummaryChange = (val: string) => {
		setLocalSummary(val);
		onChangeSummary?.(val);
	};

	/** Handles image deletion from edit mode: removes the ![alt](src) markdown tag and directly updates local summary */
	const handleDeleteImage = (src: string, altText?: string) => {
		const currentContent =
			localSummary ||
			(firstAssistantIndex >= 0 ? messages[firstAssistantIndex]?.content : "") ||
			aiSummary ||
			knowledge?.ai_summary ||
			"";
		if (!currentContent || !src) return;

		// Normalize src: strip resolved backend base URL to get the relative path as stored in markdown
		const backendBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(/\/api\/?$/, "");
		let normalizedSrc = src.trim();
		if (normalizedSrc.startsWith(backendBase)) {
			normalizedSrc = normalizedSrc.slice(backendBase.length);
		}
		// Also try decoded version (resolveImageUrl encodes spaces as %20)
		const decodedSrc = decodeURIComponent(normalizedSrc);

		// Build a list of src variants to try matching against
		const srcVariants = [normalizedSrc, decodedSrc, src.trim()];
		// Add encoded variant if different
		const encodedSrc = encodeURI(decodedSrc);
		if (!srcVariants.includes(encodedSrc)) srcVariants.push(encodedSrc);

		let updated = currentContent;
		for (const variant of srcVariants) {
			if (updated !== currentContent) break; // already matched
			const escapedSrc = variant.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
			// Remove markdown image tag: ![alt](src) or ![alt](src "title"), allowing flexible spaces/newlines
			const exactPattern = new RegExp(`!\\[[^\\]]*\\]\\s*\\(\\s*${escapedSrc}(?:\\s+["'][^"']*["'])?\\s*\\)`, "g");
			updated = currentContent.replace(exactPattern, "");
			// Also try matching standard HTML img tag if any
			if (updated === currentContent) {
				const htmlPattern = new RegExp(`<img[^>]*${escapedSrc}[^>]*\\/?>`, "gi");
				updated = currentContent.replace(htmlPattern, "");
			}
		}

		// If none of the exact URL variants matched, fallback to basename filename matching
		if (updated === currentContent) {
			const filename = normalizedSrc.split("/").pop()?.split("?")[0];
			if (filename && filename.length > 3) {
				const escapedFile = filename.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
				const filePattern = new RegExp(`!\\[[^\\]]*\\]\\s*\\([^)]*${escapedFile}[^)]*\\)`, "g");
				updated = currentContent.replace(filePattern, "");
				if (updated === currentContent) {
					const htmlFilePattern = new RegExp(`<img[^>]*${escapedFile}[^>]*\\/?>`, "gi");
					updated = currentContent.replace(htmlFilePattern, "");
				}
			}
		}

		// Also try matching by exact alt text if provided and still unchanged
		if (updated === currentContent && altText && altText.trim().length > 2) {
			const escapedAlt = altText.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
			const altPattern = new RegExp(`!\\[\\s*${escapedAlt}\\s*\\]\\s*\\([^)]*\\)`, "g");
			updated = currentContent.replace(altPattern, "");
		}

		updated = updated.replace(/\n{3,}/g, "\n\n").trim();
		handleSummaryChange(updated);
		setManualEditRevision((r) => r + 1);
	};

	const handleStartManualEdit = (currentDisplayContent: string) => {
		const rawText = localSummary || currentDisplayContent;
		const initialText = rawText.replace(/!\[([^\]]*)\]\s*\n+\s*\(([^)]+)\)/g, "![$1]($2)");
		setBackupManualSummary(initialText);
		setLocalSummary(initialText);
		setManualEditRevision((r) => r + 1);
		setIsManualEditing(true);
	};

	const handleCancelManualEdit = () => {
		setLocalSummary(backupManualSummary);
		onChangeSummary?.(backupManualSummary);
		setIsManualEditing(false);
	};

	const handleSaveManualEdit = (newSummary?: string) => {
		const finalVal = typeof newSummary === "string" ? newSummary : localSummary;
		handleSummaryChange(finalVal);
		setBackupManualSummary(finalVal);
		setIsManualEditing(false);
	};

	const [prevScopeId, setPrevScopeId] = useState(`${knowledgeId}-${sessionId}`);
	const [chatTurns, setChatTurns] = useState<Message[]>([]);
	const [initialSnapshotMap, setInitialSnapshotMap] = useState<Record<string, string>>({});
	const [streamedDocs, setStreamedDocs] = useState<Record<string, boolean>>({});
	const prevStatusRef = useRef<string | undefined>(knowledgeStatus);

	// Trigger smooth streaming typewriter animation when newly completed from PROCESSING -> PENDING
	useEffect(() => {
		if (prevStatusRef.current === "PROCESSING" && knowledgeStatus === "PENDING" && knowledgeId) {
			const timer = setTimeout(() => {
				setStreamedDocs((prev) => ({ ...prev, [knowledgeId]: true }));
			}, 0);
			return () => clearTimeout(timer);
		}
		prevStatusRef.current = knowledgeStatus;
	}, [knowledgeStatus, knowledgeId]);

	// Capture initial summary snapshot once per knowledgeId so Turn 0 is permanently immutable
	useEffect(() => {
		if (knowledgeId && (knowledge?.ai_summary || aiSummary)) {
			const meta = knowledge?.metadata as Record<string, unknown> | undefined;
			const summary = (meta?.initial_summary as string) || knowledge?.ai_summary || aiSummary;
			if (summary) {
				const timer = setTimeout(() => {
					setInitialSnapshotMap((prev) => {
						if (prev[knowledgeId] && prev[knowledgeId] === summary) return prev;
						return { ...prev, [knowledgeId]: summary };
					});
				}, 0);
				return () => clearTimeout(timer);
			}
		}
	}, [knowledgeId, knowledge?.ai_summary, knowledge?.metadata, aiSummary]);

	// Reset active session chat turns and manual edit mode when exiting edit mode
	useEffect(() => {
		if (!isEditMode) {
			const timer = setTimeout(() => {
				setIsManualEditing(false);
				if (knowledgeStatus === "APPROVED") {
					setChatTurns([]);
				}
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [isEditMode, knowledgeStatus]);

	if (prevScopeId !== `${knowledgeId}-${sessionId}`) {
		setPrevScopeId(`${knowledgeId}-${sessionId}`);
		setChatTurns([]);
	}

	const initialMsgs = useMemo(() => {
		if (mode !== "knowledge") return [];
		return getInitialMessages(
			knowledge,
			knowledgeStatus,
			isEditMode,
			aiSummary,
			fileName,
			initialPrompt,
			knowledgeId ? initialSnapshotMap[knowledgeId] : undefined,
		);
	}, [
		mode,
		knowledge,
		knowledgeStatus,
		isEditMode,
		aiSummary,
		fileName,
		initialPrompt,
		knowledgeId,
		initialSnapshotMap,
	]);

	const sessionMessages = generalSession?.messages;
	const dbMessages: Message[] = useMemo(() => {
		if (mode === "general" && sessionMessages) {
			return sessionMessages.map((m) => {
				const att = m.attachments as Record<string, unknown> | undefined;
				const opStat =
					(m as { operation_status?: string | null }).operation_status ||
					(att?.operation_status as string) ||
					undefined;
				if (m.role === "user") {
					const cleaned = cleanMessageTurn(m.content || "");
					return {
						role: "user",
						content: cleaned.content || "",
						attachmentName: cleaned.attachmentName,
						attachmentNames: cleaned.attachmentNames,
						action: m.action || undefined,
						type: m.type || (att?.type as string) || undefined,
						operation_id: m.operation_id || (att?.operation_id as string) || undefined,
						operation_status: opStat,
						attachments: att,
						target_knowledge_id: m.target_knowledge_id || undefined,
						total_found: m.total_found ?? undefined,
					};
				}
				return {
					role: m.role as "user" | "assistant",
					content: m.content || "",
					action: m.action || undefined,
					type: m.type || (att?.type as string) || undefined,
					operation_id: m.operation_id || (att?.operation_id as string) || undefined,
					operation_status: opStat,
					attachments: att,
					target_knowledge_id: m.target_knowledge_id || undefined,
					total_found: m.total_found ?? undefined,
				};
			});
		}
		return [];
	}, [mode, sessionMessages]);

	// Permanently restore confirmed/cancelled status across page navigation and session re-entry
	useEffect(() => {
		if (dbMessages && dbMessages.length > 0) {
			const restored: Record<string, "confirmed" | "cancelled"> = {};
			for (const m of dbMessages) {
				const opId = m.operation_id || (m.attachments?.operation_id as string);
				const opStatus = m.operation_status || (m.attachments?.operation_status as string);
				if (opId) {
					if (opStatus === "confirmed" || opStatus === "cancelled") {
						restored[opId] = opStatus as "confirmed" | "cancelled";
					} else if (
						m.action === "edit_applied" ||
						m.action === "delete_applied" ||
						(m.attachments?.action as string) === "edit_applied" ||
						(m.attachments?.action as string) === "delete_applied"
					) {
						restored[opId] = "confirmed";
					} else if (
						m.action === "cancelled" ||
						(m.attachments?.action as string) === "cancelled"
					) {
						restored[opId] = "cancelled";
					}
				}
			}
			if (Object.keys(restored).length > 0) {
				const timer = setTimeout(() => {
					setCompletedOps((prev) => ({ ...restored, ...prev }));
				}, 0);
				return () => clearTimeout(timer);
			}
		}
	}, [dbMessages]);

	const [input, setInput] = useState("");
	const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
	const [fileInputKey, setFileInputKey] = useState(0);
	const [isLoading, setIsLoading] = useState(false);
	const [optimisticUserMsg, setOptimisticUserMsg] = useState<Message | null>(null);
	const [activeTab, setActiveTab] = useState<string | null>(null);

	const isProcessing = isLoading;

	const currentTab =
		activeTab || (files && files.length > 0 ? (files[0].file_name as string) : null);

	const fileInputId = useId();
	const fileInputRef = useRef<HTMLInputElement>(null);
	const textareaRef = useRef<HTMLTextAreaElement>(null);
	const queryClient = useQueryClient();
	const [isDragging, setIsDragging] = useState(false);
	const dragCounter = useRef(0);
	const initialPromptTriggeredRef = useRef<string | null>(null);
	const abortControllerRef = useRef<AbortController | null>(null);
	const viewportRef = useRef<HTMLDivElement>(null);
	const isSubmittingRef = useRef(false);

	const isFailedState =
		knowledgeStatus === "REJECTED" ||
		(knowledge?.metadata as Record<string, unknown> | undefined)?.status === "FAILED" ||
		(typeof knowledge?.ai_summary === "string" &&
			knowledge.ai_summary.startsWith("[Gagal Diproses]"));

	const failureErrorMsg =
		((knowledge?.metadata as Record<string, unknown> | undefined)?.error as string) ||
		(typeof knowledge?.ai_summary === "string" &&
		knowledge.ai_summary.startsWith("[Gagal Diproses]")
			? knowledge.ai_summary
			: "Document processing failed. The file format may be corrupted, password-protected, or unsupported.");

	const handleStop = () => {
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
			abortControllerRef.current = null;
		}
		setIsLoading(false);
		setOptimisticUserMsg(null);
		toast.info("AI generation stopped.");
	};

	// Always ensure viewport scroll starts at the very top (0) in knowledge mode on mount and on document/file switch
	useEffect(() => {
		if (mode === "knowledge" && viewportRef.current) {
			viewportRef.current.scrollTop = 0;
			const raf = requestAnimationFrame(() => {
				if (viewportRef.current) {
					viewportRef.current.scrollTop = 0;
					viewportRef.current.scrollTo({ top: 0, behavior: "instant" });
				}
			});
			return () => cancelAnimationFrame(raf);
		}
	}, [knowledgeId, fileName, mode]);

	// Focus chat textarea without auto-scrolling the viewport when entering prompt edit mode
	useEffect(() => {
		if (isEditMode && !isManualEditing && textareaRef.current) {
			textareaRef.current.focus({ preventScroll: true });
		}
	}, [isEditMode, isManualEditing]);

	useEffect(() => {
		if (
			mode === "general" &&
			initialPrompt &&
			initialPromptTriggeredRef.current !== initialPrompt
		) {
			initialPromptTriggeredRef.current = initialPrompt;

			// If sessionId exists, use persistent DB endpoint
			if (sessionId) {
				const sendInitialDB = async () => {
					setIsLoading(true);
					setOptimisticUserMsg({ role: "user", content: initialPrompt });
					const controller = new AbortController();
					abortControllerRef.current = controller;
					try {
						await sendGeneralMsg.mutateAsync({ prompt: initialPrompt, signal: controller.signal });
					} catch (err: unknown) {
						const isCanceled =
							(err as { name?: string; code?: string })?.name === "CanceledError" ||
							(err as { name?: string; code?: string })?.code === "ERR_CANCELED";
						if (!isCanceled) {
							toast.error("Failed to send message to AI.");
						}
					} finally {
						abortControllerRef.current = null;
						sendGeneralMsg.reset();
						setIsLoading(false);
						setOptimisticUserMsg(null);
						// Clean URL query parameter so refresh won't re-trigger
						if (typeof window !== "undefined") {
							window.history.replaceState(
								null,
								"",
								`/dashboard/ingest/chat?session_id=${sessionId}`,
							);
						}
					}
				};
				void sendInitialDB();
			} else {
				const sendInitialStateless = async () => {
					const userMsg: Message = { role: "user", content: initialPrompt };
					setChatTurns([userMsg]);
					setIsLoading(true);
					const controller = new AbortController();
					abortControllerRef.current = controller;
					try {
						const response = await api.post(
							"/knowledge/query-general",
							{
								prompt: initialPrompt,
								history: [],
							},
							{ signal: controller.signal },
						);
						const data = response.data;
						setChatTurns([
							userMsg,
							{
								role: "assistant",
								content: data.answer,
								action: data.action,
								target_knowledge_id: data.target_knowledge_id,
								total_found: data.total_found,
							},
						]);
					} catch (err: unknown) {
						const isCanceled =
							(err as { name?: string; code?: string })?.name === "CanceledError" ||
							(err as { name?: string; code?: string })?.code === "ERR_CANCELED";
						if (!isCanceled) {
							toast.error("Failed to send message to AI.");
						}
					} finally {
						abortControllerRef.current = null;
						setIsLoading(false);
					}
				};
				void sendInitialStateless();
			}
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [mode, initialPrompt, sessionId]);

	const getFileIconAndColor = (filename?: string | null) => {
		if (!filename)
			return { Icon: RiFileTextLine, bgColor: "bg-blue-50", textColor: "text-blue-600" };
		const ext = filename.split(".").pop()?.toLowerCase() || "";
		switch (ext) {
			case "pdf":
				return { Icon: RiFilePdf2Line, bgColor: "bg-red-50", textColor: "text-red-600" };
			case "doc":
			case "docx":
				return { Icon: RiFileWord2Line, bgColor: "bg-blue-50", textColor: "text-blue-600" };
			case "xls":
			case "xlsx":
			case "csv":
				return { Icon: RiFileExcel2Line, bgColor: "bg-emerald-50", textColor: "text-emerald-600" };
			case "ppt":
			case "pptx":
			case "pps":
			case "ppsx":
			case "pot":
			case "potx":
			case "odp":
				return { Icon: RiFilePpt2Line, bgColor: "bg-orange-50", textColor: "text-orange-600" };
			case "png":
			case "jpg":
			case "jpeg":
			case "gif":
			case "webp":
				return { Icon: RiImage2Line, bgColor: "bg-purple-50", textColor: "text-purple-600" };
			case "txt":
			default:
				return { Icon: RiFileTextLine, bgColor: "bg-blue-50", textColor: "text-blue-600" };
		}
	};

	const formatFileSize = (bytes?: number | null) => {
		if (!bytes || bytes <= 0) return "0 B";
		if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB";
		if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
		if (bytes >= 1024) return (bytes / 1024).toFixed(1) + " KB";
		return bytes + " B";
	};

	const scrollToBottomAndFocus = () => {
		setTimeout(() => {
			if (viewportRef.current) {
				viewportRef.current.scrollTo({
					top: viewportRef.current.scrollHeight,
					behavior: "smooth",
				});
			}
			textareaRef.current?.focus();
		}, 60);
	};

	const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (isInputDisabled) return;

		if (e.dataTransfer.types && Array.from(e.dataTransfer.types).includes("Files")) {
			dragCounter.current += 1;
			setIsDragging(true);
		}
	};

	const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (isInputDisabled) return;

		dragCounter.current -= 1;
		if (dragCounter.current <= 0) {
			dragCounter.current = 0;
			setIsDragging(false);
		}
	};

	const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (isInputDisabled) return;

		if (e.dataTransfer) {
			e.dataTransfer.dropEffect = "copy";
		}
	};

	const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		if (isInputDisabled) return;

		dragCounter.current = 0;
		setIsDragging(false);

		if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
			setAttachedFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
			setFileInputKey((k) => k + 1);
			textareaRef.current?.focus({ preventScroll: true });
		}
	};

	const handlePaste = (e: React.ClipboardEvent) => {
		if (isInputDisabled) return;
		if (e.clipboardData.files && e.clipboardData.files.length > 0) {
			e.preventDefault();
			setAttachedFiles((prev) => [...prev, ...Array.from(e.clipboardData.files)]);
			setFileInputKey((k) => k + 1);
			textareaRef.current?.focus({ preventScroll: true });
		}
	};

	const messages: Message[] = [];
	if (mode === "general" && sessionId) {
		messages.push(...dbMessages);
	} else if (mode === "knowledge") {
		// Prevent duplicate turns if initialMsgs already absorbed the turns from server metadata
		const k = chatTurns.length;
		if (k > 0 && initialMsgs.length >= k) {
			const recentInitial = initialMsgs.slice(-k);
			const isFullyAbsorbed = recentInitial.every(
				(init, idx) => init.role === chatTurns[idx].role && init.content.trim() === chatTurns[idx].content.trim()
			);
			if (isFullyAbsorbed) {
				messages.push(...initialMsgs);
			} else {
				const lastInitial = initialMsgs[initialMsgs.length - 1];
				if (lastInitial && chatTurns[0].role === lastInitial.role && chatTurns[0].content.trim() === lastInitial.content.trim()) {
					messages.push(...initialMsgs, ...chatTurns.slice(1));
				} else {
					messages.push(...initialMsgs, ...chatTurns);
				}
			}
		} else {
			messages.push(...initialMsgs, ...chatTurns);
		}
	} else {
		messages.push(...chatTurns);
	}
	if (optimisticUserMsg) {
		messages.push(optimisticUserMsg);
	}
	const firstAssistantIndex = messages.findIndex((m) => m.role === "assistant");
	let lastAssistantIndex = -1;
	for (let i = messages.length - 1; i >= 0; i--) {
		if (messages[i].role === "assistant") {
			lastAssistantIndex = i;
			break;
		}
	}

	const renderConfidenceScore = () => {
		if (!knowledge || mode === "general") return null;
		const meta = knowledge.metadata as Record<string, unknown> | undefined;
		const rawTextAccuracy =
			(meta?.text_accuracy as string | number | undefined) ||
			(meta?.ai_confidence as string | number | undefined) ||
			(meta?.confidence_score as string | number | undefined);
		let parsedMetaAccuracy: number | undefined = undefined;
		if (typeof rawTextAccuracy === "string") {
			const cleaned = parseFloat(rawTextAccuracy.replace("%", "").trim());
			if (!isNaN(cleaned)) parsedMetaAccuracy = cleaned;
		} else if (typeof rawTextAccuracy === "number") {
			parsedMetaAccuracy = rawTextAccuracy;
		}

		let confidence =
			knowledge.ai_confidence !== null &&
			knowledge.ai_confidence !== undefined &&
			Number(knowledge.ai_confidence) > 0
				? Number(knowledge.ai_confidence)
				: (parsedMetaAccuracy ?? (knowledge.ai_confidence !== null && knowledge.ai_confidence !== undefined ? Number(knowledge.ai_confidence) : undefined));

		if (confidence !== undefined && confidence > 0 && confidence <= 1.0) {
			confidence = confidence * 100;
		}

		const isProcessing = knowledgeStatus === "PROCESSING" || knowledge.status === "PROCESSING";

		const numConfidence = confidence !== null && confidence !== undefined ? Number(confidence) : 0;
		const clampedPercent = Math.min(100, Math.max(0, numConfidence));

		const docTitle =
			title ||
			knowledge.title ||
			(fileName
				? fileName
						.replace(/\.[^/.]+$/, "")
						.replace(/[_-]/g, " ")
						.replace(/\b\w/g, (c) => c.toUpperCase())
				: "Knowledge Document");

		const docFileName = fileName || knowledge.file_name || "document.pdf";
		const ext = docFileName.includes(".")
			? docFileName.split(".").pop()?.toUpperCase() || "DOC"
			: "DOC";
		const { Icon: DocIcon } = getFileIconAndColor(docFileName);
		const status = (knowledgeStatus || knowledge.status || "PENDING").toUpperCase();

		const renderStatusBadge = () => {
			switch (status) {
				case "PENDING":
					return (
						<span className="bg-amber-50 text-amber-800 border border-amber-200/80 px-2.5 py-0.5 rounded-md text-xs font-medium">
							On review
						</span>
					);
				case "APPROVED":
					return (
						<span className="bg-emerald-50 text-emerald-800 border border-emerald-200/80 px-2.5 py-0.5 rounded-md text-xs font-medium">
							Approved
						</span>
					);
				case "PROCESSING":
					return (
						<span className="bg-blue-50 text-blue-800 border border-blue-200/80 px-2.5 py-0.5 rounded-md text-xs font-medium animate-pulse">
							Processing
						</span>
					);
				case "REJECTED":
					return (
						<span className="bg-red-50 text-red-800 border border-red-200/80 px-2.5 py-0.5 rounded-md text-xs font-medium">
							Rejected
						</span>
					);
				default:
					return (
						<span className="bg-zinc-50 text-zinc-700 border border-zinc-200 px-2.5 py-0.5 rounded-md text-xs font-medium">
							{status}
						</span>
					);
			}
		};

		return (
			<div className="flex flex-col gap-3 mb-6 w-full">
				{/* Title and Status Row */}
				<div className="flex items-start justify-between gap-4 w-full">
					<h2 className="text-base font-semibold text-zinc-900 leading-snug">{docTitle}</h2>
					<div className="shrink-0">{renderStatusBadge()}</div>
				</div>

				{/* Document Type with Icon */}
				<div className="flex items-center gap-1.5 text-zinc-500 text-xs font-medium">
					<DocIcon className="size-4 text-zinc-400" />
					<span>{ext}</span>
				</div>

				{/* Text Accuracy & Progress Bar */}
				{((confidence !== null && confidence !== undefined) || isProcessing) && (
					<div className="flex flex-col gap-2 w-full mt-1">
						<div className="flex items-center justify-between text-sm w-full font-medium">
							<span className="text-zinc-800">Text Accuracy</span>
							<span className="text-blue-600">
								{confidence !== null && confidence !== undefined
									? `${numConfidence}%`
									: isProcessing
										? "Calculating..."
										: "—"}
							</span>
						</div>
						<div className="w-full bg-blue-100/60 h-2 rounded-full overflow-hidden">
							<div
								className="bg-blue-600 h-full rounded-full transition-all duration-300"
								style={{ width: `${clampedPercent}%` }}
							/>
						</div>
					</div>
				)}
			</div>
		);
	};

	const renderCategoriesBlock = (standalone = false) => {
		if (mode === "general") return null;
		const shouldShow =
			knowledgeStatus !== "PROCESSING" &&
			(categories.length > 0 ||
				(isEditMode && knowledgeStatus === "APPROVED") ||
				knowledgeStatus === "PENDING");

		const content = (
			<div className={`flex flex-col gap-4 w-full mt-4 ${!shouldShow ? "hidden" : ""}`}>
				<CategorySettings
					categories={categories}
					onChangeCategories={(c) => onChangeCategories?.(c)}
					isEditMode={isEditMode || knowledgeStatus === "PENDING"}
					showSaveActions={isEditMode}
				/>
				{visibilitySettings && onChangeVisibilitySettings && (
					<VisibilitySettingsUI
						settings={visibilitySettings}
						onChange={onChangeVisibilitySettings}
						isEditMode={isEditMode || knowledgeStatus === "PENDING"}
						showSaveActions={isEditMode}
					/>
				)}

				{knowledge && (
					<ApprovalActions
						knowledge={knowledge}
						pendingCategories={categories}
						pendingVisibilitySettings={visibilitySettings}
						pendingTitle={title}
						pendingSummary={localSummary || summaryValue || aiSummary || undefined}
						pendingChunks={chunks}
					/>
				)}
				{files && files.length > 0 && (
					<div className="mt-8 border rounded-lg overflow-hidden bg-zinc-50 border-zinc-200">
						<div className="flex border-b border-zinc-200 bg-white overflow-x-auto scrollbar-hide">
							{files.map((f, i) => (
								<button
									key={i}
									onClick={() => setActiveTab(f.file_name as string)}
									className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors ${
										currentTab === f.file_name
											? "border-b-2 border-blue-600 text-blue-700 bg-blue-50/50"
											: "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-50"
									}`}
								>
									<RiFileTextLine className="inline-block w-4 h-4 mr-2 align-text-bottom" />
									{f.file_name as string}
								</button>
							))}
						</div>
						<div className="p-5 max-h-100 overflow-y-auto prose prose-sm max-w-none text-zinc-700">
							{files.find((f) => f.file_name === currentTab) ? (
								<div>
									<h4 className="text-zinc-900 font-semibold mb-3">Individual Summary</h4>
									<MarkdownContent
										content={
											(files.find((f) => f.file_name === currentTab)?.summary as string) ||
											"No summary available."
										}
									/>
								</div>
							) : (
								<p className="text-zinc-500 italic">Select a document to view its details.</p>
							)}
						</div>
					</div>
				)}
			</div>
		);

		return standalone ? (
			<MessageScrollerItem key="categories-block">{content}</MessageScrollerItem>
		) : (
			content
		);
	};

	const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
		const files = e.target.files;
		if (files && files.length > 0) {
			setAttachedFiles((prev) => [...prev, ...Array.from(files)]);
			textareaRef.current?.focus({ preventScroll: true });
		}
		setFileInputKey((k) => k + 1);
	};

	const removeAttachedFile = (indexToRemove: number) => {
		setAttachedFiles((prev) => prev.filter((_, idx) => idx !== indexToRemove));
		setFileInputKey((k) => k + 1);
		textareaRef.current?.focus({ preventScroll: true });
	};

	const handleSend = async () => {
		if (isSubmittingRef.current) return;
		if ((!input.trim() && attachedFiles.length === 0) || isProcessing) return;

		isSubmittingRef.current = true;

		const filesToSend = [...attachedFiles];
		const fileNames = filesToSend.map((f) => f.name);
		const userMsg: Message = {
			role: "user",
			content:
				input.trim() || (fileNames.length > 0 ? `Attached files: ${fileNames.join(", ")}` : ""),
			attachmentNames: fileNames.length > 0 ? fileNames : undefined,
			attachmentName: fileNames.length > 0 ? fileNames[0] : undefined,
		};

		if (!sessionId) {
			setChatTurns((prev) => [...prev, userMsg]);
		} else if (mode === "general") {
			setOptimisticUserMsg(userMsg);
		}
		setInput("");
		setAttachedFiles([]);
		setFileInputKey((k) => k + 1);
		setIsLoading(true);
		if (textareaRef.current) {
			textareaRef.current.style.height = "auto";
		}
		scrollToBottomAndFocus();

		const controller = new AbortController();
		abortControllerRef.current = controller;

		try {
			if (mode === "general") {
				if (sessionId) {
					await sendGeneralMsg.mutateAsync({
						prompt: userMsg.content,
						attachments: userMsg.attachmentNames ? { names: userMsg.attachmentNames } : undefined,
						signal: controller.signal,
					});
				} else {
					const response = await api.post(
						"/knowledge/query-general",
						{
							prompt: userMsg.content,
							history: messages.map((m) => ({ role: m.role, content: m.content })),
						},
						{ signal: controller.signal },
					);
					const data = response.data;
					setChatTurns((prev) => [
						...prev,
						{
							role: "assistant",
							content: data.answer || data.message || "",
							action: data.action,
							type: data.type,
							operation_id: data.operation_id,
							target_knowledge_id: data.target_knowledge_id,
							total_found: data.total_found,
						},
					]);
					if (data.action === "edit_applied" || data.action === "delete_applied") {
						invalidateAllKnowledgeQueries(queryClient, {
							knowledgeId: data.target_knowledge_id,
							knowledgeIds: data.affected_knowledge_ids,
						});
						if (data.action === "delete_applied") {
							setInitialSnapshotMap((prev) => {
								const next = { ...prev };
								if (data.target_knowledge_id) delete next[data.target_knowledge_id];
								if (knowledgeId) delete next[knowledgeId];
								if (Array.isArray(data.affected_knowledge_ids)) {
									for (const kid of data.affected_knowledge_ids) {
										delete next[kid];
									}
								}
								return next;
							});
						}
					}
				}
			} else if (
				(mode === "knowledge" ||
					knowledgeStatus === "PENDING" ||
					knowledgeStatus === "APPROVED" ||
					isEditMode ||
					filesToSend.length > 0) &&
				knowledgeId
			) {
				const endpoint = `/knowledge/${knowledgeId}/refine`;

				let response;
				if (filesToSend.length > 0) {
					const formData = new FormData();
					formData.append("prompt", userMsg.content);
					formData.append("history", JSON.stringify([...messages, userMsg]));
					formData.append("file", filesToSend[0]);
					formData.append("attached_file", filesToSend[0]);

					response = await api.post(endpoint, formData, {
						signal: controller.signal,
					});
				} else {
					response = await api.post(
						endpoint,
						{
							prompt: userMsg.content,
							history: [...messages, userMsg],
						},
						{ signal: controller.signal },
					);
				}
				const isRetrievalOnly = Boolean(response.data.is_retrieval);
				const chatResponse =
					response.data.reply ||
					response.data.feedback ||
					response.data.answer ||
					"Dokumen knowledge base telah berhasil diperbarui.";
				setChatTurns((prev) => [...prev, { role: "assistant", content: chatResponse }]);
				scrollToBottomAndFocus();
				if (response.data.summary && !isRetrievalOnly) {
					handleSummaryChange(response.data.summary);
				}
				if (response.data.title && !isRetrievalOnly && typeof onChangeTitle === "function") {
					onChangeTitle(response.data.title);
				}
				if (
					response.data.chunks &&
					!isRetrievalOnly &&
					typeof onChangeChunks === "function" &&
					Array.isArray(response.data.chunks)
				) {
					onChangeChunks(response.data.chunks);
				}
				if (
					response.data.categories &&
					!isRetrievalOnly &&
					typeof onChangeCategories === "function" &&
					Array.isArray(response.data.categories)
				) {
					onChangeCategories(response.data.categories);
				}

				if (knowledgeId) {
					invalidateAllKnowledgeQueries(queryClient, { knowledgeId });
				}

				// Clear local chatTurns after successful refine:
				// The server persists the full conversation in metadata.edit_history,
				// and after query invalidation, initialMsgs will rebuild from that
				// server metadata. Keeping chatTurns would cause duplicate messages.
				setTimeout(() => setChatTurns([]), 300);
			} else {
				const response = await api.post(
					"/knowledge/chat",
					{
						query: userMsg.content,
						knowledge_id: knowledgeId,
						history: messages,
					},
					{ signal: controller.signal },
				);

				setChatTurns((prev) => [
					...prev,
					{ role: "assistant", content: response.data?.answer || response.data?.message || "" },
				]);
			}
		} catch (err: unknown) {
			const isCanceled =
				(err as { name?: string; code?: string })?.name === "CanceledError" ||
				(err as { name?: string; code?: string })?.code === "ERR_CANCELED";
			if (!isCanceled) {
				const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
					?.detail;
				toast.error(detail || "Failed to send message to AI.");
			}
		} finally {
			abortControllerRef.current = null;
			sendGeneralMsg.reset();
			setIsLoading(false);
			setOptimisticUserMsg(null);
			isSubmittingRef.current = false;
		}
	};

	const isLiveChat =
		(mode === "general" && messages.length > 0) ||
		(mode === "knowledge" && (chatTurns.length > 0 || optimisticUserMsg !== null));

	const handleConfirmOperation = async (opId: string) => {
		setActiveOpId(opId);
		setActiveOpAction("confirm");
		try {
			const res = await confirmOp.mutateAsync({
				operationId: opId,
				sessionId: mode === "general" ? sessionId : null,
			});
			setCompletedOps((prev) => ({ ...prev, [opId]: "confirmed" }));

			const isDeleteOp =
				res.action?.toLowerCase().includes("delete") ||
				messages.some((m) => m.operation_id === opId && m.action?.toLowerCase().includes("delete"));

			const targetItem =
				res.target_item ||
				messages.find((m) => m.operation_id === opId)?.target_item ||
				(
					messages.find((m) => m.operation_id === opId)?.attachments as
						| Record<string, unknown>
						| undefined
				)?.target_item;

			if (isDeleteOp) {
				// 1. Clear initialSnapshotMap so Turn 0 updates to clean state
				setInitialSnapshotMap((prev) => {
					const next = { ...prev };
					if (knowledgeId) delete next[knowledgeId];
					if (res.target_knowledge_id) delete next[res.target_knowledge_id];
					if (Array.isArray(res.affected_knowledge_ids)) {
						for (const kid of res.affected_knowledge_ids) {
							delete next[kid];
						}
					}
					return next;
				});

				// 2. Surgically clean localSummary if targetItem was deleted
				if (typeof targetItem === "string" && targetItem.trim()) {
					setLocalSummary((prev) => {
						const cleaned = cleanDeletedItemFromMarkdown(prev, targetItem);
						onChangeSummary?.(cleaned);
						return cleaned;
					});
				}

				// 3. Surgically clean previous chat turns so deleted product does not linger in UI
				if (typeof targetItem === "string" && targetItem.trim()) {
					setChatTurns((prev) =>
						prev
							.map((turn) => {
								if (turn.role === "assistant" && turn.content) {
									return {
										...turn,
										content: cleanDeletedItemFromMarkdown(turn.content, targetItem),
									};
								}
								return turn;
							})
							.filter((turn) => {
								if (turn.role === "assistant") {
									const stripped = turn.content.replace(/^[#|\-*\s:\d.]+/g, "").trim();
									return turn.action === res.action || stripped.length >= 15;
								}
								return true;
							}),
					);
				}

				// 4. Invalidate all knowledge queries immediately
				await invalidateAllKnowledgeQueries(queryClient, {
					knowledgeId: res.target_knowledge_id || knowledgeId,
					knowledgeIds: res.affected_knowledge_ids,
					batchId: res.batch_id,
					sessionId: mode === "general" ? sessionId : null,
				});
			}

			if (mode !== "general" || !sessionId) {
				setChatTurns((prev) => [
					...prev,
					{
						role: "assistant",
						content: res.message || "",
						action: res.action,
					},
				]);
			}
		} finally {
			setActiveOpId(null);
			setActiveOpAction(null);
		}
	};

	const handleCancelOperation = async (opId: string) => {
		setActiveOpId(opId);
		setActiveOpAction("cancel");
		try {
			const res = await cancelOp.mutateAsync({
				operationId: opId,
				sessionId: mode === "general" ? sessionId : null,
			});
			setCompletedOps((prev) => ({ ...prev, [opId]: "cancelled" }));
			if (mode !== "general" || !sessionId) {
				setChatTurns((prev) => [
					...prev,
					{
						role: "assistant",
						content: res.message || "",
						action: "cancelled",
					},
				]);
			}
		} finally {
			setActiveOpId(null);
			setActiveOpAction(null);
		}
	};

	const renderOperationActions = (msg: Message) => {
		if (!msg.operation_id || msg.role !== "assistant") return null;
		const opId = msg.operation_id;
		const status =
			completedOps[opId] || msg.operation_status || (msg.attachments?.operation_status as string);
		const isPending = activeOpId === opId;
		const isConfirming = isPending && activeOpAction === "confirm";
		const isCancelling = isPending && activeOpAction === "cancel";
		const isDelete = msg.action?.toLowerCase().includes("delete");

		if (status === "confirmed") {
			return (
				<div className="mt-3.5 rounded-lg border border-emerald-200/80 bg-emerald-50/70 p-3 text-xs sm:text-sm text-emerald-900 font-medium flex items-center justify-between gap-2 shadow-none">
					<div className="flex items-center gap-2">
						<RiCheckboxCircleFill className="size-4 text-emerald-600 shrink-0" />
						<span>
							{typeof (msg.attachments as Record<string, unknown>)?.success_message === "string"
								? ((msg.attachments as Record<string, unknown>).success_message as string)
								: "Changes successfully confirmed and applied to Knowledge Base."}
						</span>
					</div>
					<span className="text-[11px] font-semibold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-md border border-emerald-200/80 shrink-0">
						Applied
					</span>
				</div>
			);
		}

		if (status === "cancelled") {
			return (
				<div className="mt-3.5 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs sm:text-sm text-zinc-700 font-medium flex items-center justify-between gap-2 shadow-none">
					<div className="flex items-center gap-2">
						<RiCloseCircleLine className="size-4 text-zinc-500 shrink-0" />
						<span>Operation has been cancelled.</span>
					</div>
					<span className="text-[11px] font-semibold text-zinc-600 bg-zinc-200/70 px-2 py-0.5 rounded-md border border-zinc-300 shrink-0">
						Cancelled
					</span>
				</div>
			);
		}

		return (
			<div className="mt-3.5 pt-3.5 border-t border-zinc-200/80 flex flex-wrap items-center justify-between gap-3 bg-zinc-50/80 p-3 rounded-lg shadow-none">
				<div className="flex items-center gap-2 text-xs text-zinc-600">
					<span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200/80">
						Action Required
					</span>
					<span className="font-normal text-zinc-600">Confirm to apply proposed changes</span>
				</div>
				<div className="flex items-center gap-2">
					<Button
						type="button"
						variant="outline"
						disabled={isPending || isProcessing}
						onClick={() => handleCancelOperation(opId)}
						className="h-9 px-4 text-xs sm:text-sm font-medium border-zinc-300 hover:bg-zinc-100 text-zinc-700 rounded-lg shadow-none gap-1.5 cursor-pointer transition-colors"
					>
						{isCancelling ? (
							<RiLoader4Line className="size-4 animate-spin" />
						) : (
							<RiCloseLine className="size-4" />
						)}
						Cancel
					</Button>
					<Button
						type="button"
						disabled={isPending || isProcessing}
						onClick={() => handleConfirmOperation(opId)}
						className={`h-9 px-4 text-xs sm:text-sm font-medium rounded-lg shadow-none gap-1.5 cursor-pointer transition-colors ${
							isDelete
								? "bg-red-600 hover:bg-red-700 text-white focus:ring-red-500"
								: "bg-blue-600 hover:bg-blue-700 text-white focus:ring-blue-500"
						}`}
					>
						{isConfirming ? (
							<RiLoader4Line className="size-4 animate-spin" />
						) : isDelete ? (
							<RiDeleteBin7Line className="size-4" />
						) : (
							<RiCheckLine className="size-4" />
						)}
						{isDelete ? "Confirm & Delete" : "Confirm & Apply"}
					</Button>
				</div>
			</div>
		);
	};

	const renderAssistantContent = (index: number, msg: Message) => {
		const isInitialTurn = index === firstAssistantIndex;
		const isPendingDoc = (knowledgeStatus || knowledge?.status || "").toUpperCase() === "PENDING";
		const isTargetForEdit =
			isInitialTurn && mode === "knowledge" && (isPendingDoc || isEditMode || isManualEditing);
		const displayContent = isInitialTurn
			? localSummary || msg.content || aiSummary || knowledge?.ai_summary || ""
			: msg.content || "";

		if (isTargetForEdit) {
			if (!isManualEditing) {
				return (
					<div className="flex flex-col w-full">
						{index === firstAssistantIndex && headerNode}
						{index === firstAssistantIndex && renderConfidenceScore()}

						{/* Primary Manual Edit Trigger Button */}
						<div className="flex items-center justify-end mb-3">
							<Button
								type="button"
								size="sm"
								variant="default"
								onClick={() => handleStartManualEdit(displayContent)}
								className="gap-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-none h-8 px-3 font-medium text-xs transition-colors cursor-pointer"
							>
								<RiEdit2Line className="size-3.5" />
								Manual Edit
							</Button>
						</div>

						<MarkdownContent content={displayContent} onDeleteImage={handleDeleteImage} />
						{renderOperationActions(msg)}
					</div>
				);
			}

			// Manual Direct Edit Mode with TipTap WYSIWYG Editor
			return (
				<div className="flex flex-col w-full my-2 gap-2">
					{(() => {
						const text = localSummary || displayContent || "";
						const matches = Array.from(text.matchAll(/!\[([^\]]*)\]\s*\n*\s*\(([^)]+)\)/g));
						const seen = new Set<string>();
						const docImages: { alt: string; url: string }[] = [];
						for (const m of matches) {
							const u = (m[2] || "").trim();
							if (u && !seen.has(u)) {
								seen.add(u);
								docImages.push({ alt: (m[1] || "").trim(), url: u });
							}
						}
						if (docImages.length === 0) return null;
						return (
							<div className="flex flex-col gap-2 p-3 bg-blue-50/70 border border-blue-200/90 rounded-xl shadow-xs">
								<div className="flex items-center gap-2">
									<div className="size-6 rounded-md bg-blue-600 text-white flex items-center justify-center shrink-0">
										<RiImage2Line className="size-3.5" />
									</div>
									<span className="text-xs font-semibold text-blue-950">
										Foto Terdeteksi ({docImages.length} foto)
									</span>
									<span className="text-[11px] text-blue-700 hidden sm:inline">
										— Foto visual dalam dokumen. Klik ikon sampah merah untuk menghapus foto dari dokumen.
									</span>
								</div>
								<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 pt-1">
									{docImages.map((img, idx) => (
										<div
											key={idx}
											className="flex items-center gap-2.5 bg-white border border-blue-200/80 rounded-lg p-2 shadow-xs hover:border-blue-400 transition-colors"
										>
											{/* eslint-disable-next-line @next/next/no-img-element */}
											<img
												src={resolveImageUrl(img.url)}
												alt={img.alt || `Gambar ${idx + 1}`}
												className="size-14 object-contain rounded-md border border-zinc-200 bg-zinc-50 shrink-0"
												onError={(e) => {
													(e.currentTarget as HTMLElement).style.display = "none";
												}}
											/>
											<div className="flex flex-col flex-1 min-w-0 pr-1">
												<span className="text-xs font-semibold text-zinc-900 truncate" title={img.alt}>
													{img.alt || `Gambar ${idx + 1}`}
												</span>
												<span className="text-[10px] text-zinc-400 font-mono truncate" title={img.url}>
													{img.url.split("/").pop()}
												</span>
												<span className="text-[10px] text-emerald-600 font-medium">
													✓ Terhubung ke dokumen
												</span>
											</div>
											<button
												type="button"
												onClick={(e) => {
													e.stopPropagation();
													e.preventDefault();
													handleDeleteImage(img.url, img.alt);
												}}
												className="size-8 rounded-lg bg-red-50 hover:bg-red-600 text-red-600 hover:text-white border border-red-200 hover:border-red-600 flex items-center justify-center shrink-0 cursor-pointer transition-colors shadow-xs"
												title={`Hapus foto ${img.alt || ""}`}
											>
												<RiDeleteBin7Line className="size-4" />
											</button>
										</div>
									))}
								</div>
							</div>
						);
					})()}

					<WysiwygEditor
						key={manualEditRevision}
						initialContent={localSummary || displayContent}
						onSave={(markdown) => handleSaveManualEdit(markdown)}
						onCancel={handleCancelManualEdit}
					/>
				</div>
			);
		}

		return (
			<div className="flex flex-col w-full">
				{index === firstAssistantIndex && headerNode}
				{index === firstAssistantIndex && renderConfidenceScore()}
				<StreamingMarkdown
					content={msg.content || ""}
					animate={index === firstAssistantIndex && streamedDocs[knowledgeId || ""] === true}
					onFinished={() => {
						if (knowledgeId) {
							setStreamedDocs((prev) => ({ ...prev, [knowledgeId]: false }));
						}
					}}
				/>
				{renderOperationActions(msg)}
			</div>
		);
	};

	const isApprovedDoc = (knowledgeStatus || knowledge?.status || "").toUpperCase() === "APPROVED";

	const isInputDisabled =
		mode === "general"
			? isProcessing
			: knowledgeStatus === "PROCESSING" ||
				isProcessing ||
				isDetailLoading ||
				(isApprovedDoc && !isEditMode);

	return (
		<div
			className="flex flex-col flex-1 bg-white overflow-hidden min-h-0 h-full relative"
			onDragEnter={handleDragEnter}
			onDragLeave={handleDragLeave}
			onDragOver={handleDragOver}
			onDrop={handleDrop}
			onPaste={handlePaste}
		>
			<MessageScrollerProvider>
				<MessageScroller className="flex-1 min-h-0">
					<MessageScrollerViewport ref={viewportRef} className="px-6 sm:px-8">
						<MessageScrollerContent className="py-8 gap-6 w-full max-w-5xl mx-auto min-w-0">
							{isDetailLoading && (
								<MessageScrollerItem>
									<div className="flex items-start gap-3 w-full min-w-0 max-w-full">
										<div className="bg-zinc-100 rounded-lg text-zinc-950 flex items-center justify-center p-2 mt-0.5 shrink-0 shadow-none">
											<RiRobot2Line className="size-4 animate-pulse text-blue-500" />
										</div>
										<div className="bg-blue-50/70 text-zinc-950 p-3 rounded-lg text-sm w-full min-w-0 max-w-full flex items-center gap-2 border border-blue-100/50 shadow-none">
											<RiLoader4Line className="size-4 animate-spin text-blue-600" />
											<span className="text-zinc-700 font-medium">
												Fetching document details and session...
											</span>
										</div>
									</div>
								</MessageScrollerItem>
							)}

							{isFailedState && (
								<MessageScrollerItem>
									<div className="flex flex-col w-full min-w-0 max-w-full gap-3">
										{headerNode}
										<div className="flex items-start gap-3 w-full min-w-0 max-w-full">
											<div className="bg-red-50 rounded-lg text-red-600 flex items-center justify-center p-2.5 mt-0.5 shrink-0 border border-red-200 shadow-none">
												<RiAlertLine className="size-5 text-red-600" />
											</div>
											<div className="bg-red-50/70 text-zinc-950 p-4 rounded-lg text-sm w-full min-w-0 max-w-full border border-red-200 flex flex-col gap-3 shadow-none">
												<div className="flex items-center justify-between">
													<span className="font-semibold text-red-700 text-sm">
														Document Processing Failed
													</span>
												</div>
												<p className="text-xs text-zinc-700 leading-relaxed font-mono bg-white p-3 rounded-lg border border-red-200/80 shadow-none">
													{failureErrorMsg}
												</p>
												<p className="text-[11px] text-zinc-600 leading-relaxed">
													Please check if the file is password-protected, corrupted, or re-upload
													the document in a standard format (PDF, DOCX, XLSX, TXT, Images).
												</p>

												<div className="flex flex-wrap items-center gap-2 pt-1">
													<input
														ref={retryFileInputRef}
														type="file"
														className="hidden"
														accept=".docx,.pptx,.xlsx,.pdf,.txt,.csv,.png,.jpg,.jpeg,.webp"
														onChange={handleRetryFileSelected}
													/>
													<Button
														type="button"
														onClick={() => retryFileInputRef.current?.click()}
														disabled={isReplacingFile || replaceFileMutation.isPending}
														className="gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-3.5 h-8 text-xs font-medium cursor-pointer shadow-none"
													>
														{isReplacingFile || replaceFileMutation.isPending ? (
															<>
																<RiLoader4Line className="size-4 animate-spin" />
																Uploading Replacement...
															</>
														) : (
															<>
																<RiUploadCloud2Line className="size-4" />
																Replace File & Retry
															</>
														)}
													</Button>
												</div>
											</div>
										</div>
									</div>
								</MessageScrollerItem>
							)}

							{!isDetailLoading &&
								!isFailedState &&
								messages.length === 0 &&
								knowledgeStatus !== "PROCESSING" && (
									<MessageScrollerItem>
										{mode === "general" ? (
											<div className="flex flex-col items-center justify-center text-center py-16 px-4 max-w-lg mx-auto space-y-3">
												<div className="size-12 rounded-lg bg-blue-50 text-blue-500 flex items-center justify-center">
													<RiRobot2Line className="size-6" />
												</div>
												<h2 className="text-base font-semibold text-zinc-950">
													Knowledge Base Assistant
												</h2>
												<p className="text-xs text-zinc-500 leading-relaxed">
													Ask questions about clinic products and treatments, instruct updates, or
													clean expired records. The assistant maintains context across your
													conversation.
												</p>
											</div>
										) : (
											<div className="flex items-start gap-3 w-full min-w-0 max-w-full">
												<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
													<RiRobot2Line className="size-4" />
												</div>
												<div className="bg-blue-50/80 text-zinc-950 p-4 rounded-md text-sm w-full min-w-0 max-w-full border border-blue-100 flex flex-col gap-3">
													{headerNode}
													{renderConfidenceScore()}
													<p className="text-zinc-500 italic">No summary available.</p>
												</div>
											</div>
										)}
									</MessageScrollerItem>
								)}

							{!isDetailLoading && knowledgeStatus === "PROCESSING" && (
								<MessageScrollerItem>
									<div className="flex flex-col w-full min-w-0 max-w-full items-start">
										{/* Attached Document Badge OUTSIDE & ABOVE bubble if no user message shown */}
										{preHeaderNode
											? preHeaderNode
											: fileName &&
												messages.length === 0 &&
												(() => {
													const { Icon, bgColor, textColor } = getFileIconAndColor(fileName);
													return (
														<div className="flex flex-col gap-2 mb-4 self-end">
															<Attachment className="bg-white border border-zinc-200 shadow-none p-1.5 w-fit min-w-40 max-w-sm rounded-lg">
																<AttachmentMedia
																	className={`${bgColor} ${textColor} shrink-0 rounded-lg p-2`}
																>
																	<Icon className="size-5" />
																</AttachmentMedia>
																<AttachmentContent className="overflow-hidden min-w-0 pr-2">
																	<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate block">
																		{fileName}
																	</AttachmentTitle>
																	<span className="text-[11px] text-zinc-500 uppercase font-medium">
																		{/\.(png|jpe?g|webp|gif|svg)$/i.test(fileName || "")
																			? "IMAGE"
																			: "DOCUMENT"}
																	</span>
																</AttachmentContent>
															</Attachment>
														</div>
													);
												})()}

										<ProcessingPipelineCard headerNode={headerNode} fileName={fileName} />
									</div>
								</MessageScrollerItem>
							)}

							{messages.length > 0 && (
								<MessageScrollerItem
									key="msg-0"
									scrollAnchor={isLiveChat && messages.length === 1 && !isLoading}
								>
									<div
										className={`flex flex-col w-full min-w-0 max-w-full ${messages[0].role === "user" ? "items-end" : "items-start"}`}
									>
										{title !== undefined && onChangeTitle && (
											<div className="flex justify-center w-full mb-4">
												<div className="w-fit max-w-lg">
													<TitleSettings
														title={title}
														onChangeTitle={onChangeTitle}
														isEditMode={isEditMode || knowledgeStatus === "PENDING"}
													/>
												</div>
											</div>
										)}
										{fileName &&
											!preHeaderNode &&
											messages[0].role !== "user" &&
											(() => {
												const { Icon, bgColor, textColor } = getFileIconAndColor(fileName);
												return (
													<div className="flex flex-col gap-2 mb-4 self-end">
														<Attachment className="bg-white border border-zinc-200 shadow-none p-1.5 w-fit min-w-40 max-w-sm rounded-lg">
															<AttachmentMedia
																className={`${bgColor} ${textColor} shrink-0 rounded-lg p-2`}
															>
																<Icon className="size-5" />
															</AttachmentMedia>
															<AttachmentContent className="overflow-hidden min-w-0 pr-2">
																<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate block">
																	{fileName}
																</AttachmentTitle>
																<AttachmentDescription className="text-[11px] text-zinc-500 uppercase">
																	{/\.(png|jpe?g|webp|gif|svg)$/i.test(fileName || "")
																		? "IMAGE"
																		: "DOCUMENT"}
																</AttachmentDescription>
															</AttachmentContent>
														</Attachment>
													</div>
												);
											})()}
										{(() => {
											const names =
												messages[0].attachmentNames ||
												(messages[0].attachmentName ? [messages[0].attachmentName] : []);
											if (names.length === 0 || preHeaderNode) return null;
											return (
												<div className="flex flex-wrap gap-2 mb-2">
													{names.map((name, i) => {
														const { Icon, bgColor, textColor } = getFileIconAndColor(name);
														return (
															<Attachment
																key={i}
																className="bg-white border border-zinc-200 shadow-none p-1.5 min-w-35 max-w-50 shrink-0 rounded-lg"
															>
																<AttachmentMedia
																	className={`${bgColor} ${textColor} rounded-lg p-2 shrink-0`}
																>
																	<Icon className="w-5 h-5" />
																</AttachmentMedia>
																<AttachmentContent className="overflow-hidden min-w-0 pr-2">
																	<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate block">
																		{name}
																	</AttachmentTitle>
																	<AttachmentDescription className="text-[11px] text-zinc-500 uppercase">
																		{/\.(png|jpe?g|webp|gif|svg)$/i.test(name || "")
																			? "IMAGE"
																			: "DOCUMENT"}
																	</AttachmentDescription>
																</AttachmentContent>
															</Attachment>
														);
													})}
												</div>
											);
										})()}
										{preHeaderNode}
										<div
											className={`flex items-start gap-3 w-full min-w-0 max-w-full ${messages[0].role === "user" ? "flex-row-reverse" : ""}`}
										>
											<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
												{messages[0].role === "user" ? (
													<RiUser3Line className="size-4" />
												) : (
													<RiRobot2Line className="size-4" />
												)}
											</div>
											<div
												className={`${messages[0].role === "user" ? "bg-primary text-primary-foreground whitespace-pre-wrap max-w-[85%] sm:max-w-[75%] rounded-md" : "bg-transparent border border-zinc-200 text-zinc-950 w-full rounded-md"} p-3.5 text-sm min-w-0 overflow-hidden`}
											>
												{messages[0].role === "assistant"
													? renderAssistantContent(0, messages[0])
													: messages[0].content || ""}
												{/* Inject Categories below initial summary if it's the latest assistant message */}
												{0 === lastAssistantIndex && renderCategoriesBlock()}
											</div>
										</div>
									</div>
								</MessageScrollerItem>
							)}

							{/* Categories Section (Fallback: if no messages exist at all but we need to show categories) */}
							{messages.length === 0 && renderCategoriesBlock(true)}

							{/* Render remaining messages */}
							{messages.slice(1).map((msg, sliceIndex) => {
								const actualIndex = sliceIndex + 1;
								return (
									<MessageScrollerItem
										key={`msg-${actualIndex}`}
										scrollAnchor={isLiveChat && actualIndex === messages.length - 1 && !isLoading}
									>
										<div
											className={`flex flex-col w-full min-w-0 max-w-full ${msg.role === "user" ? "items-end" : "items-start"}`}
										>
											{(() => {
												const names =
													msg.attachmentNames || (msg.attachmentName ? [msg.attachmentName] : []);
												if (names.length === 0) return null;
												return (
													<div className="flex flex-wrap gap-2 mb-2">
														{names.map((name, i) => {
															const { Icon, bgColor, textColor } = getFileIconAndColor(name);
															return (
																<Attachment
																	key={i}
																	className="bg-white border border-zinc-200 shadow-none p-1.5 min-w-35 max-w-50 shrink-0 rounded-lg"
																>
																	<AttachmentMedia
																		className={`${bgColor} ${textColor} rounded-lg p-2 shrink-0`}
																	>
																		<Icon className="w-5 h-5" />
																	</AttachmentMedia>
																	<AttachmentContent className="overflow-hidden min-w-0 pr-2">
																		<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate block">
																			{name}
																		</AttachmentTitle>
																		<AttachmentDescription className="text-[11px] text-zinc-500 uppercase">
																			{/\.(png|jpe?g|webp|gif|svg)$/i.test(name || "")
																				? "IMAGE"
																				: "DOCUMENT"}
																		</AttachmentDescription>
																	</AttachmentContent>
																</Attachment>
															);
														})}
													</div>
												);
											})()}
											<div
												className={`flex items-start gap-3 w-full min-w-0 max-w-full ${msg.role === "user" ? "flex-row-reverse" : ""}`}
											>
												<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
													{msg.role === "user" ? (
														<RiUser3Line className="size-4" />
													) : (
														<RiRobot2Line className="size-4" />
													)}
												</div>
												<div
													className={`${msg.role === "user" ? "bg-primary text-primary-foreground whitespace-pre-wrap max-w-[85%] sm:max-w-[75%] rounded-md" : "bg-transparent border border-zinc-200 text-zinc-950 w-full rounded-md"} p-3.5 text-sm min-w-0 overflow-hidden`}
												>
													{msg.role === "assistant"
														? renderAssistantContent(actualIndex, msg)
														: msg.content || ""}
													{/* Inject Categories below this AI message if it's the latest assistant message */}
													{actualIndex === lastAssistantIndex && renderCategoriesBlock()}
												</div>
											</div>
										</div>
									</MessageScrollerItem>
								);
							})}

							{isLoading && (
								<MessageScrollerItem scrollAnchor>
									<div className="flex items-start gap-3 w-full">
										<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
											<RiRobot2Line className="size-4 text-blue-600" />
										</div>
										<div className="bg-transparent border border-zinc-200 rounded-md px-3.5 py-3 text-sm min-w-0 flex items-center gap-1.5">
											<span className="size-1.5 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.3s]" />
											<span className="size-1.5 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.15s]" />
											<span className="size-1.5 rounded-full bg-blue-600 animate-bounce" />
										</div>
									</div>
								</MessageScrollerItem>
							)}
						</MessageScrollerContent>
					</MessageScrollerViewport>
					<MessageScrollerSmartButton />
				</MessageScroller>
			</MessageScrollerProvider>

			{/* Chatbox Input */}
			<div className="px-6 sm:px-8 py-4 shrink-0 w-full">
				<div
					className={`max-w-5xl mx-auto relative rounded-lg p-4 flex flex-col gap-3 transition-colors border shadow-none ${
						isDragging
							? "border-blue-500 bg-blue-50/50"
							: isInputDisabled
								? "border-zinc-200 bg-zinc-50/60"
								: "border-zinc-200 bg-white"
					}`}
					onDragEnter={handleDragEnter}
					onDragLeave={handleDragLeave}
					onDragOver={handleDragOver}
					onDrop={handleDrop}
					onPaste={handlePaste}
				>
					{/* Drag & Drop Visual Overlay (Compact inside chatbox) */}
					{isDragging && (
						<div className="absolute inset-0 z-30 flex flex-col items-center justify-center rounded-md border-2 border-dashed border-blue-500 bg-blue-50/95 pointer-events-none gap-2 p-4 text-center">
							<div className="flex items-center justify-center size-10 rounded-full bg-blue-100 text-blue-600">
								<RiUploadCloud2Line className="size-5" />
							</div>
							<div className="flex flex-col items-center gap-0.5">
								<span className="text-xs font-semibold text-zinc-900">
									Drop file here to attach
								</span>
								<span className="text-[11px] text-zinc-500">
									Release to add file to your message
								</span>
							</div>
							<div className="flex items-center gap-1.5 text-[10px]">
								<span className="px-1.5 py-0.5 rounded bg-white border border-blue-200 font-medium text-zinc-700">
									PDF
								</span>
								<span className="px-1.5 py-0.5 rounded bg-white border border-blue-200 font-medium text-zinc-700">
									DOCX
								</span>
								<span className="px-1.5 py-0.5 rounded bg-white border border-blue-200 font-medium text-zinc-700">
									PPTX
								</span>
								<span className="px-1.5 py-0.5 rounded bg-white border border-blue-200 font-medium text-zinc-700">
									XLSX
								</span>
								<span className="px-1.5 py-0.5 rounded bg-white border border-blue-200 font-medium text-zinc-700">
									Images
								</span>
							</div>
						</div>
					)}

					{/* File Attachment Cards Preview in Input */}
					{attachedFiles.length > 0 && (
						<div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar">
							{attachedFiles.map((file, idx) => {
								const { Icon, bgColor, textColor } = getFileIconAndColor(file.name);
								return (
									<Attachment
										key={idx}
										className="bg-white border border-zinc-200 shadow-none p-1.5 min-w-35 max-w-50 shrink-0 rounded-lg"
									>
										<AttachmentMedia className={`${bgColor} ${textColor} rounded-lg p-2 shrink-0`}>
											<Icon className="w-5 h-5" />
										</AttachmentMedia>
										<AttachmentContent className="overflow-hidden min-w-0 pr-1">
											<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate block">
												{file.name}
											</AttachmentTitle>
											<AttachmentDescription className="text-[11px] text-zinc-500">
												{formatFileSize(file.size)}
											</AttachmentDescription>
										</AttachmentContent>
										<AttachmentActions>
											<AttachmentAction
												type="button"
												variant="ghost"
												className="hover:bg-zinc-100 text-zinc-500 hover:text-zinc-950 ml-1 cursor-pointer"
												onClick={(e) => {
													e.stopPropagation();
													removeAttachedFile(idx);
												}}
											>
												<RiCloseLine className="w-4 h-4" />
											</AttachmentAction>
										</AttachmentActions>
									</Attachment>
								);
							})}
						</div>
					)}

					<textarea
						ref={textareaRef}
						rows={1}
						value={input}
						onChange={(e) => {
							setInput(e.target.value);
							e.target.style.height = "auto";
							e.target.style.height = `${e.target.scrollHeight}px`;
						}}
						onKeyDown={(e) => {
							if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
								e.preventDefault();
								if (!isSubmittingRef.current) {
									handleSend();
								}
							} else if (e.key === "Escape") {
								e.currentTarget.blur();
							}
						}}
						placeholder={
							knowledgeStatus === "PROCESSING"
								? "Waiting for ingestion to complete..."
								: isApprovedDoc && !isEditMode
									? "Click 'Edit Knowledge' to ask questions or request adjustments..."
									: mode === "general"
										? "Ask about the knowledge..."
										: "Ask questions or request adjustments..."
						}
						disabled={isInputDisabled}
						className="w-full bg-transparent resize-none border-none shadow-none focus-visible:ring-0 px-0 outline-none text-sm text-zinc-900 placeholder:text-zinc-500 max-h-32 overflow-y-auto custom-scrollbar disabled:opacity-50 disabled:cursor-not-allowed"
					/>

					<input
						key={fileInputKey}
						id={fileInputId}
						type="file"
						ref={fileInputRef}
						onChange={handleFileSelect}
						disabled={isInputDisabled}
						multiple
						className="sr-only"
					/>

					<div
						className={`flex items-center ${mode === "general" ? "justify-end" : "justify-between"} pt-1`}
					>
						{mode !== "general" && (
							<label
								htmlFor={isInputDisabled ? undefined : fileInputId}
								className={`inline-flex items-center justify-center size-8 rounded-md text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 transition-colors ${
									isInputDisabled
										? "opacity-40 cursor-not-allowed pointer-events-none"
										: "cursor-pointer"
								}`}
								title={isInputDisabled ? "Input disabled" : "Attach files"}
							>
								<RiAttachment2 className="size-4 pointer-events-none shrink-0" />
							</label>
						)}
						{isProcessing ? (
							<Button
								type="button"
								onClick={handleStop}
								size="icon"
								title="Stop AI Generation"
								className="bg-red-600 text-white hover:bg-red-700 shrink-0 rounded-lg shadow-none cursor-pointer"
							>
								<RiStopCircleLine className="w-4 h-4" />
							</Button>
						) : (
							<Button
								onClick={handleSend}
								disabled={isInputDisabled || (!input.trim() && attachedFiles.length === 0)}
								size="icon"
								title="Send (Enter) • New line (Shift+Enter)"
								className="bg-blue-600 text-white hover:bg-blue-700 shrink-0 rounded-lg shadow-none cursor-pointer disabled:opacity-50"
							>
								<RiCornerDownLeftLine className="w-4 h-4" />
							</Button>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}
