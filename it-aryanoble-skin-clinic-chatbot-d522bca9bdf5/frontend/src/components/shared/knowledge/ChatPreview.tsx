import { knowledgeKeys } from "@/app/dashboard/knowledge/api/keys";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	MessageScroller,
	MessageScrollerButton,
	MessageScrollerContent,
	MessageScrollerItem,
	MessageScrollerProvider,
	MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import {
	Attachment,
	AttachmentMedia,
	AttachmentContent,
	AttachmentTitle,
	AttachmentDescription,
} from "@/components/ui/attachment";
import { api } from "@/lib/axios";
import {
	RiAttachment2,
	RiCheckLine,
	RiCloseLine,
	RiCornerDownLeftLine,
	RiFilePdf2Line,
	RiFileTextLine,
	RiLoader4Line,
	RiRobot2Line,
	RiUser3Line,
} from "@remixicon/react";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

interface ChatPreviewProps {
	knowledgeId?: string;
	knowledgeStatus?: string;
	aiSummary?: string | null;
	fileName?: string | null;
	isDetailLoading?: boolean;
	isEditMode?: boolean;
}

interface Message {
	role: "user" | "assistant";
	content: string;
	attachmentName?: string;
}

export function ChatPreview({
	knowledgeId,
	knowledgeStatus,
	aiSummary,
	fileName,
	isDetailLoading,
	isEditMode,
}: ChatPreviewProps) {
	const STORAGE_KEY = `chat_preview_${knowledgeId || 'default'}`;

	const [userChatMessages, setUserChatMessages] = useState<Message[]>(() => {
		if (typeof window !== "undefined") {
			const saved = localStorage.getItem(STORAGE_KEY);
			if (saved) {
				try {
					return JSON.parse(saved);
				} catch (e) {
					console.error("Failed to parse chat messages", e);
				}
			}
		}
		return [];
	});

	const [input, setInput] = useState("");
	const [attachedFile, setAttachedFile] = useState<File | null>(null);
	const [isLoading, setIsLoading] = useState(false);
	const fileInputRef = useRef<HTMLInputElement>(null);
	const queryClient = useQueryClient();

	useEffect(() => {
		if (typeof window !== "undefined") {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(userChatMessages));
		}
	}, [userChatMessages, STORAGE_KEY]);

	const initialSummaryMessage: Message | null =
		aiSummary && knowledgeStatus !== "PROCESSING"
			? { role: "assistant", content: aiSummary }
			: null;

	const messages: Message[] = initialSummaryMessage
		? [initialSummaryMessage, ...userChatMessages]
		: userChatMessages;

	const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
		if (e.target.files && e.target.files[0]) {
			setAttachedFile(e.target.files[0]);
		}
	};

	const handleSend = async () => {
		if ((!input.trim() && !attachedFile) || isLoading) return;

		const userMsg: Message = {
			role: "user",
			content: input.trim() || (attachedFile ? `Attached file: ${attachedFile.name}` : ""),
			attachmentName: attachedFile ? attachedFile.name : undefined,
		};

		setUserChatMessages((prev) => [...prev, userMsg]);
		setInput("");
		setAttachedFile(null);
		setIsLoading(true);

		try {
			if ((knowledgeStatus === "PENDING" || (knowledgeStatus === "APPROVED" && isEditMode)) && knowledgeId) {
				const endpoint = knowledgeStatus === "PENDING" 
					? `/ai/ingest/pending/${knowledgeId}/refine`
					: `/ai/ingest/approved/${knowledgeId}/refine`;
					
				const response = await api.post(endpoint, {
					prompt: userMsg.content,
				});
				const chatResponse = response.data.summary
					? `Here is the updated summary:\n\n${response.data.summary}`
					: "I've updated the document summary based on your instructions.";
				setUserChatMessages((prev) => [...prev, { role: "assistant", content: chatResponse }]);

				if (knowledgeId) {
					queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(knowledgeId) });
				}
			} else {
				const response = await api.post("/ai/chat", {
					query: userMsg.content,
					knowledge_id: knowledgeId,
					history: messages,
				});

				setUserChatMessages((prev) => [
					...prev,
					{ role: "assistant", content: response.data.answer },
				]);
			}
		} catch {
			toast.error("Failed to send message to AI.");
		} finally {
			setIsLoading(false);
		}
	};

	const isInputDisabled = knowledgeStatus === "PROCESSING" || isLoading || isDetailLoading || (knowledgeStatus === "APPROVED" && !isEditMode);

	return (
		<div className="flex flex-col flex-1 bg-white overflow-hidden min-h-0 h-full">
			<MessageScrollerProvider>
				<MessageScroller className="flex-1 min-h-0">
					<MessageScrollerViewport className="px-8">
						<MessageScrollerContent className="py-10 gap-6 w-full max-w-4xl mx-auto">
							{isDetailLoading && (
								<MessageScrollerItem>
									<div className="flex items-start gap-3 w-full">
										<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
											<RiRobot2Line className="size-4 animate-pulse text-blue-500" />
										</div>
										<div className="bg-blue-50/70 text-zinc-950 p-3 rounded-md text-sm w-full flex items-center gap-2 border border-blue-100/50">
											<RiLoader4Line className="size-4 animate-spin text-blue-600" />
											<span className="text-zinc-700 font-medium">
												Fetching document details and session...
											</span>
										</div>
									</div>
								</MessageScrollerItem>
							)}

							{!isDetailLoading && messages.length === 0 && knowledgeStatus !== "PROCESSING" && (
								<div className="flex flex-col items-center justify-center text-zinc-500 h-full pt-20">
									<RiRobot2Line className="size-10 mb-4 text-zinc-300" />
									<p>Ask anything about this document...</p>
								</div>
							)}

							{!isDetailLoading && knowledgeStatus === "PROCESSING" && messages.length === 0 && (
								<MessageScrollerItem>
									<div className="flex flex-col w-full items-start">
										{/* Attached Document Badge OUTSIDE & ABOVE bubble */}
										{fileName && (
											<Attachment className="bg-white border-border shadow-sm p-1.5 w-fit min-w-40 max-w-sm mb-2">
												<AttachmentMedia className="bg-blue-50 text-blue-600 shrink-0">
													<RiFilePdf2Line className="size-5" />
												</AttachmentMedia>
												<AttachmentContent className="overflow-hidden">
													<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate">
														{fileName}
													</AttachmentTitle>
													<AttachmentDescription className="text-[11px] text-zinc-500 uppercase">
														DOCUMENT
													</AttachmentDescription>
												</AttachmentContent>
											</Attachment>
										)}

										<div className="flex items-start gap-3 w-full">
											<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
												<RiRobot2Line className="size-4" />
											</div>
											<div className="bg-blue-50/80 text-zinc-950 p-4 rounded-md text-sm w-full border border-blue-100 flex flex-col gap-3">
												<div className="flex items-center gap-2">
													<span className="relative flex h-3 w-3">
														<span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
														<span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
													</span>
													<span className="font-semibold text-blue-700">Processing Document</span>
												</div>
												<p className="text-zinc-600 text-xs leading-relaxed">
													Document processing progress:
												</p>
												<div className="flex flex-col gap-2.5 bg-white/90 rounded border border-blue-100 p-3.5 text-xs text-zinc-700">
													<div className="flex items-center gap-2.5 text-emerald-600 font-medium">
														<RiCheckLine className="size-4 shrink-0" />
														<span>1. Extracting Content</span>
													</div>
													<div className="flex items-center gap-2.5 text-emerald-600 font-medium">
														<RiCheckLine className="size-4 shrink-0" />
														<span>2. Structuring Information</span>
													</div>
													<div className="flex items-center gap-2.5 text-blue-600 font-semibold animate-pulse">
														<RiLoader4Line className="size-4 animate-spin shrink-0" />
														<span>3. Building Search Index...</span>
													</div>
													<div className="flex items-center gap-2.5 text-zinc-400">
														<span className="size-4 flex items-center justify-center text-[10px]">
															○
														</span>
														<span>4. Generating Summary</span>
													</div>
												</div>
												<span className="text-[11px] text-zinc-500 mt-0.5">
													You can navigate away anytime. Processing continues in the background.
												</span>
											</div>
										</div>
									</div>
								</MessageScrollerItem>
							)}

							{messages.map((msg, index) => (
								<MessageScrollerItem key={index}>
									<div
										className={`flex flex-col w-full ${msg.role === "user" ? "items-end" : "items-start"}`}
									>
										{/* Attached Knowledge Document Badge OUTSIDE & ABOVE initial AI summary bubble */}
										{fileName && index === 0 && msg.role === "assistant" && (
											<Attachment className="bg-white border-border shadow-sm p-1.5 w-fit min-w-40 max-w-sm mb-2">
												<AttachmentMedia className="bg-blue-50 text-blue-600 shrink-0">
													<RiFilePdf2Line className="size-5" />
												</AttachmentMedia>
												<AttachmentContent className="overflow-hidden">
													<AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate">
														{fileName}
													</AttachmentTitle>
													<AttachmentDescription className="text-[11px] text-zinc-500 uppercase">
														DOCUMENT
													</AttachmentDescription>
												</AttachmentContent>
											</Attachment>
										)}

										{/* User File Attachment Chip OUTSIDE & ABOVE user bubble */}
										{msg.attachmentName && (
											<div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-100 border border-zinc-200 rounded-md text-xs font-medium text-zinc-800 w-fit mb-2 shadow-2xs">
												<RiFileTextLine className="size-3.5 text-blue-600 shrink-0" />
												<span className="truncate max-w-xs">{msg.attachmentName}</span>
											</div>
										)}

										<div
											className={`flex items-start gap-3 w-full ${msg.role === "user" ? "flex-row-reverse" : ""}`}
										>
											<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
												{msg.role === "user" ? (
													<RiUser3Line className="size-4" />
												) : (
													<RiRobot2Line className="size-4" />
												)}
											</div>
											<div
												className={`${
													msg.role === "user" ? "bg-blue-500 text-white" : "bg-blue-50 text-zinc-950"
												} p-3.5 rounded-md text-sm w-full prose prose-sm max-w-none prose-p:leading-relaxed 
												prose-pre:bg-zinc-800 prose-pre:text-zinc-100 
												prose-p:my-1.5 prose-ul:my-1.5 prose-ul:pl-4 prose-ol:my-1.5 prose-ol:pl-4 prose-li:my-0.5 prose-headings:my-2.5 
												prose-table:w-full prose-table:border prose-table:border-blue-200/60 prose-table:rounded-md prose-table:overflow-hidden prose-table:my-3 prose-table:bg-white 
												prose-th:bg-blue-100/50 prose-th:px-3 prose-th:py-2.5 prose-th:text-left prose-th:font-semibold prose-th:text-blue-900 prose-th:border-b prose-th:border-blue-200/60 
												prose-td:px-3 prose-td:py-2.5 prose-td:border-b prose-td:border-blue-100/60 last:prose-td:border-0 whitespace-pre-wrap`}
											>
												{msg.role === "assistant" ? (
													<ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
												) : (
													msg.content
												)}
											</div>
										</div>
									</div>
								</MessageScrollerItem>
							))}

							{isLoading && (
								<MessageScrollerItem scrollAnchor>
									<div className="flex items-start gap-3 w-full">
										<div className="bg-zinc-100 rounded text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
											<RiRobot2Line className="size-4 animate-bounce text-blue-500" />
										</div>
										<div className="text-sm text-zinc-500 pt-1.5 italic animate-pulse">
											Thinking...
										</div>
									</div>
								</MessageScrollerItem>
							)}
						</MessageScrollerContent>
					</MessageScrollerViewport>
					<MessageScrollerButton />
				</MessageScroller>
			</MessageScrollerProvider>

			{/* Chatbox Input */}
			<div className="px-8 py-4 shrink-0">
				<div className="bg-white rounded-md p-4 flex flex-col gap-3 border border-black/10 shadow-xs">
					{/* File Attachment Pill Preview in Input */}
					{attachedFile && (
						<div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 text-blue-800 rounded-md text-xs font-medium w-fit">
							<RiFileTextLine className="size-3.5 text-blue-600 shrink-0" />
							<span className="truncate max-w-xs">{attachedFile.name}</span>
							<button
								type="button"
								onClick={() => setAttachedFile(null)}
								className="text-blue-600 hover:text-blue-900 ml-1 p-0.5 rounded-full hover:bg-blue-100"
							>
								<RiCloseLine className="size-3.5" />
							</button>
						</div>
					)}

					<Input
						value={input}
						onChange={(e) => setInput(e.target.value)}
						onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
						placeholder={
							knowledgeStatus === "PROCESSING"
								? "Waiting for ingestion to complete..."
								: knowledgeStatus === "APPROVED" && !isEditMode
								? "Click 'Edit Knowledge' to refine summary..."
								: "Ask questions or request adjustments..."
						}
						disabled={isInputDisabled}
						className="w-full bg-transparent border-none shadow-none focus-visible:ring-0 px-0 outline-none text-sm text-gray-700 placeholder:text-gray-500"
					/>

					<input type="file" ref={fileInputRef} onChange={handleFileSelect} className="hidden" />

					<div className="flex items-center justify-between pt-1">
						<Button
							type="button"
							variant="ghost"
							size="icon-sm"
							onClick={() => fileInputRef.current?.click()}
							disabled={isInputDisabled}
							className="text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100"
							title="Attach a file"
						>
							<RiAttachment2 className="size-4" />
						</Button>
						<Button
							onClick={handleSend}
							disabled={isInputDisabled || (!input.trim() && !attachedFile)}
							size="icon"
							className="bg-blue-500 text-white hover:bg-blue-600 shrink-0"
						>
							<RiCornerDownLeftLine className="w-4 h-4" />
						</Button>
					</div>
				</div>
			</div>
		</div>
	);
}
