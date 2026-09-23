import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./FloatingChatbot.css";

/**
 * FloatingChatbot Component
 *
 * A reference implementation for integrating the Arya Noble AI Chatbot into a React application.
 *
 * @param {Object} props
 * @param {string} props.token - The JWT token provided by the CIS system (used for authorization).
 * @param {string} props.doctorName - The name of the doctor currently logged in (for display).
 * @param {string} [props.branchCode] - The code of the branch (e.g. "011").
 * @param {string} [props.branchId] - The CIS external ID of the branch (e.g. "838").
 * @param {string} [props.apiBaseUrl] - The base URL of the Chatbot API (e.g., https://api.arya-noble.com).
 */
function isValidImageUrl(src) {
	if (!src) return false;
	const clean = src.trim().toLowerCase();
	if (
		!clean ||
		clean === "image_url" ||
		clean === "url" ||
		clean === "null" ||
		clean === "none" ||
		clean === "#" ||
		/new_image|placeholder|dummy|undefined|test_image|url_gambar|gambar_terlampir|url_/i.test(clean) ||
		clean.endsWith("/image_url") ||
		clean.endsWith("/url")
	) {
		return false;
	}
	return true;
}

function resolveImageUrl(src, apiBaseUrl) {
	if (!src) return "";
	let trimmed = src.trim();

	// Normalize hallucinated `https://api/` or `http://api/` prefixes
	if (/^https?:\/\/api\//i.test(trimmed)) {
		trimmed = trimmed.replace(/^https?:\/\/api\//i, "/api/");
	}

	if (
		trimmed.startsWith("http://") ||
		trimmed.startsWith("https://") ||
		trimmed.startsWith("data:") ||
		trimmed.startsWith("blob:")
	) {
		return encodeURI(decodeURI(trimmed));
	}

	const base = (apiBaseUrl || "http://localhost:8000").replace(/\/api\/?$/, "").replace(/\/+$/, "");
	const fullUrl = trimmed.startsWith("/") ? `${base}${trimmed}` : `${base}/${trimmed}`;
	return encodeURI(decodeURI(fullUrl));
}

function stripInternalMetadata(text) {
	if (!text) return "";
	let cleaned = text;

	// Strip supplementary attached file content blocks
	cleaned = cleaned.replace(
		/\[SUPPLEMENTARY ATTACHED FILE CONTENT:\s*['"]?[^'"\n]+['"]?\][\s\S]*?\[END OF ATTACHED FILE CONTENT\]/gi,
		"",
	);
	cleaned = cleaned.replace(
		/---\s*NEWLY ATTACHED SUPPLEMENTARY FILE:\s*['"]?[^'"\n]+['"]?\s*---[\s\S]*?---\s*END OF ATTACHED FILE CONTENT\s*---/gi,
		"",
	);

	// Normalize unencoded spaces in markdown image links ![alt](url) -> ![alt](encodedUrl)
	cleaned = cleaned.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, rawUrl) => {
		const trimmedUrl = rawUrl.trim();
		if (trimmedUrl.includes(" ")) {
			const encoded = trimmedUrl.replace(/ /g, "%20");
			return `![${alt}](${encoded})`;
		}
		return match;
	});

	// Normalize unicode bullet symbols (•, ●, ◦) to standard markdown list syntax
	cleaned = cleaned.replace(/^[ \t]*[•●◦][ \t]*/gm, "- ");

	return cleaned.trim();
}

function MarkdownImage({ src, alt, onPreview, apiBaseUrl, ...props }) {
	const [hasError, setHasError] = useState(false);
	const strSrc = typeof src === "string" ? src.trim() : "";

	if (!isValidImageUrl(strSrc)) {
		return null;
	}

	const resolvedSrc = resolveImageUrl(strSrc, apiBaseUrl);
	const altText = typeof alt === "string" && alt.trim() ? alt.trim() : "Document Image";

	if (hasError) {
		return (
			<span className="fc-img-fallback">
				<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
					<rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
					<circle cx="8.5" cy="8.5" r="1.5" />
					<polyline points="21 15 16 10 5 21" />
				</svg>
				<span>Gambar Tidak Tersedia</span>
			</span>
		);
	}

	return (
		<span className="fc-img-card" onClick={() => onPreview({ src: resolvedSrc, alt: altText })}>
			<span className="fc-img-container">
				<img
					src={resolvedSrc}
					alt={altText}
					className="fc-img-preview"
					loading="lazy"
					onError={() => setHasError(true)}
					{...props}
				/>
				<button
					type="button"
					className="fc-img-zoom-btn"
					title="Perbesar Gambar"
					onClick={(e) => {
						e.stopPropagation();
						onPreview({ src: resolvedSrc, alt: altText });
					}}
				>
					<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
						<circle cx="11" cy="11" r="8" />
						<line x1="21" y1="21" x2="16.65" y2="16.65" />
						<line x1="11" y1="8" x2="11" y2="14" />
						<line x1="8" y1="11" x2="14" y2="11" />
					</svg>
				</button>
			</span>
			{altText && altText !== "Document Image" && (
				<span className="fc-img-caption">{altText}</span>
			)}
		</span>
	);
}

function getFileIcon(filename) {
	const ext = filename?.split(".").pop()?.toLowerCase();
	if (ext === "pdf") {
		return (
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="fc-icon-pdf">
				<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
				<polyline points="14 2 14 8 20 8" />
				<line x1="16" y1="13" x2="8" y2="13" />
				<line x1="16" y1="17" x2="8" y2="17" />
				<polyline points="10 9 9 9 8 9" />
			</svg>
		);
	}
	if (["doc", "docx"].includes(ext)) {
		return (
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="fc-icon-doc">
				<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
				<polyline points="14 2 14 8 20 8" />
				<line x1="16" y1="13" x2="8" y2="13" />
				<line x1="16" y1="17" x2="8" y2="17" />
			</svg>
		);
	}
	if (["xls", "xlsx", "csv"].includes(ext)) {
		return (
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="fc-icon-xls">
				<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
				<polyline points="14 2 14 8 20 8" />
				<path d="M8 13h8M8 17h8M12 9v12" />
			</svg>
		);
	}
	if (["jpg", "jpeg", "png", "webp"].includes(ext)) {
		return (
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="fc-icon-img">
				<rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
				<circle cx="8.5" cy="8.5" r="1.5" />
				<polyline points="21 15 16 10 5 21" />
			</svg>
		);
	}
	return (
		<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="fc-icon-file">
			<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
			<polyline points="14 2 14 8 20 8" />
		</svg>
	);
}

export default function FloatingChatbot({
	token,
	doctorName = "Doctor",
	branchCode,
	branchId,
	apiBaseUrl = "http://localhost:8000",
}) {
	const [isOpen, setIsOpen] = useState(false);
	const [messages, setMessages] = useState([]);
	const [input, setInput] = useState("");
	const [sessionId, setSessionId] = useState(null);
	const [sessionStatus, setSessionStatus] = useState("ACTIVE");
	const [allowFileAttachments, setAllowFileAttachments] = useState(false);
	const [selectedFiles, setSelectedFiles] = useState([]);
	const [isLoading, setIsLoading] = useState(false);
	const [previewImage, setPreviewImage] = useState(null);

	// Feedback states
	const [rating, setRating] = useState(null);
	const [feedbackText, setFeedbackText] = useState("");
	const [dataNotFound, setDataNotFound] = useState(false);
	const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
	const [manualClose, setManualClose] = useState(false);

	const chatEndRef = useRef(null);
	const fileInputRef = useRef(null);
	const abortControllerRef = useRef(null);

	const stopGeneration = () => {
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
			abortControllerRef.current = null;
		}
		setIsLoading(false);
	};

	useEffect(() => {
		chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages]);

	const initChat = async () => {
		try {
			const res = await fetch(`${apiBaseUrl}/api/chats/`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Authorization: `Bearer ${token}`,
				},
				body: JSON.stringify({
					...(branchCode ? { branch_code: branchCode } : {}),
					...(branchId && !branchCode ? { cis_branch_id: branchId } : {}),
				}),
			});

			if (!res.ok) {
				const errData = await res.json().catch(() => ({}));
				throw new Error(errData.detail || "Failed to initialize session");
			}

			const data = await res.json();
			setSessionId(data.id);
			setSessionStatus(data.status || "ACTIVE");
			setAllowFileAttachments(Boolean(data.allow_file_attachments));

			// Fetch existing messages if resuming an active session
			const msgRes = await fetch(`${apiBaseUrl}/api/chats/${data.id}/messages`, {
				headers: { Authorization: `Bearer ${token}` },
				cache: "no-store"
			});

			if (msgRes.ok) {
				const history = await msgRes.json();
				if (history && history.length > 0) {
					setMessages(
						history.map((m) => ({
							id: m.id,
							role: m.role.toLowerCase(),
							content: m.content,
							attachments: m.attachments || null,
						})),
					);
				} else {
					setMessages([
						{
							id: "init",
							role: "assistant",
							content: "Your artificial intelligence assistant is ready.",
						},
					]);
				}
			}
		} catch (err) {
			console.error("Failed to create/resume session:", err);
			setMessages([
				{
					id: "init-error",
					role: "assistant",
					content: `Error initializing session: ${err.message}`,
				},
			]);
		}
	};

	const toggleChat = async () => {
		const nextState = !isOpen;
		setIsOpen(nextState);

		// Step 1: If opening for the first time, create a new chat session via the API
		if (nextState && !sessionId && token) {
			await initChat();
		}
	};

	const startNewChat = async () => {
		setRating(null);
		setFeedbackText("");
		setDataNotFound(false);
		setFeedbackSubmitted(false);
		setManualClose(false);
		setSessionId(null);
		setSelectedFiles([]);
		setMessages([]);
		await initChat();
	};

	const handleFileChange = (e) => {
		if (!e.target.files || e.target.files.length === 0) return;
		const filesArray = Array.from(e.target.files);
		setSelectedFiles((prev) => [...prev, ...filesArray]);
		if (fileInputRef.current) fileInputRef.current.value = "";
	};

	const handleRemoveFile = (indexToRemove) => {
		setSelectedFiles((prev) => prev.filter((_, idx) => idx !== indexToRemove));
	};

	const handleSend = async (e) => {
		if (e) e.preventDefault();
		const trimmed = input.trim();
		if ((!trimmed && selectedFiles.length === 0) || !sessionId || !token || isLoading) return;

		const currentInput = trimmed;
		const currentFiles = [...selectedFiles];
		
		const attachmentsMeta = currentFiles.length > 0
			? currentFiles.reduce((acc, f) => {
				acc[f.name] = { content_type: f.type, status: "processed" };
				return acc;
			}, {})
			: null;

		const userMessage = { 
			id: Date.now().toString(), 
			role: "user", 
			content: currentInput,
			attachments: attachmentsMeta
		};
		setMessages((prev) => [...prev, userMessage]);
		setInput("");
		setSelectedFiles([]);
		setIsLoading(true);

		const controller = new AbortController();
		abortControllerRef.current = controller;

		try {
			let res;
			if (currentFiles.length > 0) {
				const formData = new FormData();
				formData.append("role", "user");
				formData.append("content", currentInput);
				currentFiles.forEach((file) => {
					formData.append("files", file);
				});

				res = await fetch(`${apiBaseUrl}/api/chats/${sessionId}/messages`, {
					method: "POST",
					headers: {
						Authorization: `Bearer ${token}`,
					},
					body: formData,
					signal: controller.signal,
				});
			} else {
				const payload = JSON.stringify({
					role: "user",
					content: currentInput
				});

				res = await fetch(`${apiBaseUrl}/api/chats/${sessionId}/messages/stream`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Authorization: `Bearer ${token}`,
					},
					body: payload,
					signal: controller.signal,
				});
			}

			if (!res.ok) {
				const errorData = await res.json().catch(() => ({}));
				throw new Error(errorData.detail || "Failed to send message");
			}

			if (!res.body) throw new Error("ReadableStream not supported");

			const reader = res.body.getReader();
			const decoder = new TextDecoder("utf-8");
			let assistantMessageId = "ai-" + Date.now().toString();

			// Create a placeholder for the assistant message
			setMessages((prev) => [...prev, { id: assistantMessageId, role: "assistant", content: "" }]);
			setIsLoading(false); // Remove loading indicator once stream starts

			let buffer = "";

			while (true) {
				const { value, done } = await reader.read();
				if (done) break;

				buffer += decoder.decode(value, { stream: true });
				const events = buffer.split("\n\n");

				// Keep the last segment in the buffer because it might be incomplete
				buffer = events.pop() || "";

				for (let event of events) {
					event = event.trim();
					if (!event) continue;

					if (event.startsWith("data: ")) {
						const jsonStr = event.substring(6).trim();
						if (!jsonStr) continue;

						try {
							const parsedData = JSON.parse(jsonStr);

							if (parsedData.type === "token") {
								setMessages((prev) =>
									prev.map((msg) =>
										msg.id === assistantMessageId
											? { ...msg, content: msg.content + parsedData.content }
											: msg,
									),
								);
							} else if (parsedData.type === "done") {
								// The stream has ended
								break;
							} else if (parsedData.error) {
								console.error("AI Assistant Error:", parsedData.error);
								setMessages((prev) =>
									prev.map((msg) =>
										msg.id === assistantMessageId
											? { ...msg, content: msg.content + "\n\n**Error:** " + parsedData.error }
											: msg,
									),
								);
							}
							// 'context' type could be handled here if we want to show sources
						} catch (err) {
							console.error("Failed to parse SSE JSON chunk", err, "Chunk:", jsonStr);
						}
					}
				}
			}
		} catch (err) {
			setIsLoading(false);
			if (err.name === "AbortError") {
				console.log("Chat stream aborted by user");
				return;
			}
			console.error("Message send error:", err);
			
			if (err.message.toLowerCase().includes("closed") || err.message.toLowerCase().includes("expired") || err.message.includes("403")) {
				setSessionStatus("CLOSED");
				setManualClose(false); // Indicates it was a timeout, not a manual click
			} else {
				setMessages((prev) => [
					...prev,
					{
						id: "error-" + Date.now(),
						role: "assistant",
						content: `An error occurred: ${err.message}`,
					},
				]);
			}
		} finally {
			abortControllerRef.current = null;
		}
	};

	const endChat = async () => {
		if (!sessionId || !token) return;
		try {
			setManualClose(true);
			const res = await fetch(`${apiBaseUrl}/api/chats/${sessionId}`, {
				method: "PUT",
				headers: {
					"Content-Type": "application/json",
					Authorization: `Bearer ${token}`,
				},
				body: JSON.stringify({ status: "CLOSED" }),
			});
			if (res.ok) {
				setSessionStatus("CLOSED");
			}
		} catch (err) {
			console.error("Failed to end chat:", err);
		}
	};

	const submitFeedback = async (e) => {
		if (e) e.preventDefault();
		if (!sessionId || !token || !rating) return;
		try {
			await fetch(`${apiBaseUrl}/api/chats/${sessionId}`, {
				method: "PUT",
				headers: {
					"Content-Type": "application/json",
					Authorization: `Bearer ${token}`,
				},
				body: JSON.stringify({
					rating: rating,
					feedback: feedbackText,
					has_data_issue: dataNotFound,
				}),
			});
			setFeedbackSubmitted(true);
		} catch (err) {
			console.error("Failed to submit feedback:", err);
		}
	};

	return (
		<div className="fc-container">
			{/* Expanded Widget */}
			<div className={`fc-window ${isOpen ? "fc-open" : "fc-closed"}`}>
				{/* Header */}
				<div className="fc-header">
					<div className="fc-header-left">
						<div className="fc-header-icon">
							{/* Robot icon */}
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="currentColor"
								width="20"
								height="20"
							>
								<path d="M13.5 2C13.5 2.44425 13.3069 2.84339 13 3.11805V5H18C19.6569 5 21 6.34315 21 8V18C21 19.6569 19.6569 21 18 21H6C4.34315 21 3 19.6569 3 18V8C3 6.34315 4.34315 5 6 5H11V3.11805C10.6931 2.84339 10.5 2.44425 10.5 2C10.5 1.17157 11.1716 0.5 12 0.5C12.8284 0.5 13.5 1.17157 13.5 2ZM6 7C5.44772 7 5 7.44772 5 8V18C5 18.5523 5.44772 19 6 19H18C18.5523 19 19 18.5523 19 18V8C19 7.44772 18.5523 7 18 7H13H11H6ZM2 10H0V16H2V10ZM22 10H24V16H22V10ZM9 14.5C9.82843 14.5 10.5 13.8284 10.5 13C10.5 12.1716 9.82843 11.5 9 11.5C8.17157 11.5 7.5 12.1716 7.5 13C7.5 13.8284 8.17157 14.5 9 14.5ZM15 14.5C15.8284 14.5 16.5 13.8284 16.5 13C16.5 12.1716 15.8284 11.5 15 11.5C14.1716 11.5 13.5 12.1716 13.5 13C13.5 13.8284 14.1716 14.5 15 14.5Z" />
							</svg>
						</div>
						<div className="fc-header-title">
							<h3>Erha AI Assistant</h3>
							<span>{doctorName}</span>
						</div>
					</div>
					<div className="fc-header-actions">
						{sessionStatus === "ACTIVE" && (
							<button onClick={endChat} className="fc-action-btn fc-end-btn" title="End Chat">
								End
							</button>
						)}
						<button onClick={() => setIsOpen(false)} className="fc-action-btn" title="Minimize">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="currentColor"
								width="20"
								height="20"
							>
								<path d="M12 10.586l4.95-4.95 1.414 1.414-4.95 4.95 4.95 4.95-1.414 1.414-4.95-4.95-4.95 4.95-1.414-1.414 4.95-4.95-4.95-4.95L7.05 5.636z" />
							</svg>
						</button>
					</div>
				</div>

				{sessionStatus === "CLOSED" ? (
					<div className="fc-end-session-screen">
						<h2 className="fc-end-title">End of Session</h2>
						<div className="fc-end-icon">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								strokeWidth="2"
								strokeLinecap="round"
								strokeLinejoin="round"
							>
								<circle cx="12" cy="12" r="10"></circle>
								<polyline points="12 6 12 12 16 14"></polyline>
							</svg>
						</div>
						<p className="fc-end-desc">
							{manualClose
								? "This session has ended, please give a feedback so we can improve, and you will get a summary."
								: "You have reached the 5-minute limit for this session, please give this session a feedback so we can improve, and you will get a summary."}
						</p>

						{feedbackSubmitted ? (
							<div className="fc-feedback-thanks">
								<p>Thank you for your feedback!</p>
								<button 
									onClick={startNewChat}
									className="fc-submit-feedback-btn"
									style={{marginTop: '1rem'}}
								>
									Start New Chat
								</button>
							</div>
						) : (
							<div className="fc-feedback-card">
								<div className="fc-form-group">
									<label>
										Rate<span className="text-red-500">*</span>
									</label>
									<div className="fc-rating-buttons">
										<button
											type="button"
											className={`fc-rate-btn ${rating === "GOOD" ? "active" : ""}`}
											onClick={() => setRating("GOOD")}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												strokeWidth="2"
												strokeLinecap="round"
												strokeLinejoin="round"
												className="size-4"
											>
												<path d="M7 10v12" />
												<path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z" />
											</svg>
											Good
										</button>
										<button
											type="button"
											className={`fc-rate-btn ${rating === "BAD" ? "active" : ""}`}
											onClick={() => setRating("BAD")}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												strokeWidth="2"
												strokeLinecap="round"
												strokeLinejoin="round"
												className="size-4"
											>
												<path d="M17 14V2" />
												<path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z" />
											</svg>
											Bad
										</button>
									</div>
								</div>

								<div className="fc-form-group">
									<label>
										Feedback <span className="fc-optional">(opsional)</span>
									</label>
									<textarea
										placeholder="write your feedback here..."
										value={feedbackText}
										onChange={(e) => setFeedbackText(e.target.value)}
									></textarea>
								</div>

								<label className="fc-checkbox-label">
									<input
										type="checkbox"
										checked={dataNotFound}
										onChange={(e) => setDataNotFound(e.target.checked)}
									/>
									I found a "Data Not Found" issue in this chat.
								</label>

								<button
									type="button"
									className="fc-submit-feedback-btn"
									onClick={submitFeedback}
									disabled={!rating}
								>
									Send Feedback
								</button>
							</div>
						)}
					</div>
				) : (
					<>
						{/* Chat Area */}
						<div className="fc-body">
							{messages.map((msg, index) => (
								<div
									key={msg.id || index}
									className={`fc-message-row ${msg.role === "user" ? "fc-row-user" : "fc-row-assistant"}`}
								>
									<div className={`fc-message-container ${msg.role === "user" ? "fc-container-user" : "fc-container-assistant"}`}>
										{/* Avatar */}
										<div className={`fc-avatar ${msg.role === "user" ? "fc-avatar-user" : "fc-avatar-assistant"}`}>
											{msg.role === "user" ? (
												<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
													<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
													<circle cx="12" cy="7" r="4" />
												</svg>
											) : (
												<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
													<path d="M13.5 2C13.5 2.44425 13.3069 2.84339 13 3.11805V5H18C19.6569 5 21 6.34315 21 8V18C21 19.6569 19.6569 21 18 21H6C4.34315 21 3 19.6569 3 18V8C3 6.34315 4.34315 5 6 5H11V3.11805C10.6931 2.84339 10.5 2.44425 10.5 2C10.5 1.17157 11.1716 0.5 12 0.5C12.8284 0.5 13.5 1.17157 13.5 2ZM6 7C5.44772 7 5 7.44772 5 8V18C5 18.5523 5.44772 19 6 19H18C18.5523 19 19 18.5523 19 18V8C19 7.44772 18.5523 7 18 7H13H11H6ZM2 10H0V16H2V10ZM22 10H24V16H22V10ZM9 14.5C9.82843 14.5 10.5 13.8284 10.5 13C10.5 12.1716 9.82843 11.5 9 11.5C8.17157 11.5 7.5 12.1716 7.5 13C7.5 13.8284 8.17157 14.5 9 14.5ZM15 14.5C15.8284 14.5 16.5 13.8284 16.5 13C16.5 12.1716 15.8284 11.5 15 11.5C14.1716 11.5 13.5 12.1716 13.5 13C13.5 13.8284 14.1716 14.5 15 14.5Z" />
												</svg>
											)}
										</div>

										<div className="fc-bubble-wrapper">
											{/* Attachments pills if present */}
											{msg.attachments && Object.keys(msg.attachments).length > 0 && (
												<div className="fc-message-attachments">
													{Object.keys(msg.attachments).map((filename, i) => (
														<div key={i} className="fc-attachment-badge" title={filename}>
															<div className="fc-attachment-icon-box">
																{getFileIcon(filename)}
															</div>
															<div className="fc-attachment-meta">
																<span className="fc-attachment-name">{filename}</span>
																<span className="fc-attachment-tag">DOCUMENT</span>
															</div>
														</div>
													))}
												</div>
											)}

											<div className={`fc-bubble ${msg.role === "user" ? "fc-user" : "fc-assistant"}`}>
												{msg.role === "assistant" ? (
													<div className="fc-markdown-content">
														<ReactMarkdown
															remarkPlugins={[remarkGfm]}
															components={{
																img: (imgProps) => (
																	<MarkdownImage
																		{...imgProps}
																		apiBaseUrl={apiBaseUrl}
																		onPreview={setPreviewImage}
																	/>
																),
															}}
														>
															{stripInternalMetadata(msg.content)}
														</ReactMarkdown>
													</div>
												) : (
													<div className="fc-user-text">{msg.content}</div>
												)}
											</div>
										</div>
									</div>
								</div>
							))}
							{isLoading && (
								<div className="fc-message-row fc-row-assistant">
									<div className="fc-message-container fc-container-assistant">
										<div className="fc-avatar fc-avatar-assistant">
											<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
												<path d="M13.5 2C13.5 2.44425 13.3069 2.84339 13 3.11805V5H18C19.6569 5 21 6.34315 21 8V18C21 19.6569 19.6569 21 18 21H6C4.34315 21 3 19.6569 3 18V8C3 6.34315 4.34315 5 6 5H11V3.11805C10.6931 2.84339 10.5 2.44425 10.5 2C10.5 1.17157 11.1716 0.5 12 0.5C12.8284 0.5 13.5 1.17157 13.5 2ZM6 7C5.44772 7 5 7.44772 5 8V18C5 18.5523 5.44772 19 6 19H18C18.5523 19 19 18.5523 19 18V8C19 7.44772 18.5523 7 18 7H13H11H6ZM2 10H0V16H2V10ZM22 10H24V16H22V10ZM9 14.5C9.82843 14.5 10.5 13.8284 10.5 13C10.5 12.1716 9.82843 11.5 9 11.5C8.17157 11.5 7.5 12.1716 7.5 13C7.5 13.8284 8.17157 14.5 9 14.5ZM15 14.5C15.8284 14.5 16.5 13.8284 16.5 13C16.5 12.1716 15.8284 11.5 15 11.5C14.1716 11.5 13.5 12.1716 13.5 13C13.5 13.8284 14.1716 14.5 15 14.5Z" />
											</svg>
										</div>
										<div className="fc-bubble fc-assistant fc-loading">
											<div className="fc-dot"></div>
											<div className="fc-dot"></div>
											<div className="fc-dot"></div>
										</div>
									</div>
								</div>
							)}
							<div ref={chatEndRef} />
						</div>

						{/* Input Area */}
						<div className="fc-footer">
							{selectedFiles.length > 0 && (
								<div className="fc-selected-files-tray">
									{selectedFiles.map((file, idx) => (
										<div key={idx} className="fc-file-chip">
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												strokeWidth="2"
												strokeLinecap="round"
												strokeLinejoin="round"
												className="fc-chip-icon"
											>
												<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
												<polyline points="14 2 14 8 20 8"></polyline>
											</svg>
											<span className="fc-chip-name">{file.name}</span>
											<button
												type="button"
												className="fc-chip-remove"
												onClick={() => handleRemoveFile(idx)}
												title="Remove file"
											>
												×
											</button>
										</div>
									))}
								</div>
							)}
							<form onSubmit={handleSend} className="fc-input-wrapper">
								{allowFileAttachments && (
									<>
										<input
											type="file"
											ref={fileInputRef}
											onChange={handleFileChange}
											multiple
											accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.jpg,.jpeg,.png"
											style={{ display: "none" }}
											id="fc-file-input"
										/>
										<button
											type="button"
											className="fc-attach-btn"
											onClick={() => fileInputRef.current?.click()}
											disabled={isLoading || !sessionId}
											title="Attach files"
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												strokeWidth="2"
												strokeLinecap="round"
												strokeLinejoin="round"
												width="18"
												height="18"
											>
												<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
											</svg>
										</button>
									</>
								)}
								<input
									type="text"
									value={input}
									onChange={(e) => setInput(e.target.value)}
									placeholder="Describe what your concern is..."
									disabled={isLoading || !sessionId}
								/>
								{isLoading ? (
									<button
										type="button"
										onClick={stopGeneration}
										style={{ backgroundColor: "#ef4444", color: "#ffffff", border: "none", cursor: "pointer" }}
										title="Stop Generation"
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 24 24"
											fill="currentColor"
											width="18"
											height="18"
										>
											<rect x="6" y="6" width="12" height="12" rx="2" />
										</svg>
									</button>
								) : (
									<button type="submit" disabled={(!input.trim() && selectedFiles.length === 0) || !sessionId}>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 24 24"
											fill="currentColor"
											width="20"
											height="20"
										>
											<path d="M1.946 9.315c-.522-.174-.527-.455.01-.634l19.087-6.362c.529-.176.832.12.684.638l-5.454 19.086c-.15.529-.455.547-.679.045L12 14l6-8-8 6-8.054-2.685z" />
										</svg>
									</button>
								)}
							</form>
						</div>
					</>
				)}
			</div>

			{/* Minimized Button */}
			{!isOpen && (
				<button className="fc-toggle" onClick={toggleChat} aria-label="Open AI Assistant">
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 24 24"
						fill="currentColor"
						width="24"
						height="24"
					>
						<path d="M13.5 2C13.5 2.44425 13.3069 2.84339 13 3.11805V5H18C19.6569 5 21 6.34315 21 8V18C21 19.6569 19.6569 21 18 21H6C4.34315 21 3 19.6569 3 18V8C3 6.34315 4.34315 5 6 5H11V3.11805C10.6931 2.84339 10.5 2.44425 10.5 2C10.5 1.17157 11.1716 0.5 12 0.5C12.8284 0.5 13.5 1.17157 13.5 2ZM6 7C5.44772 7 5 7.44772 5 8V18C5 18.5523 5.44772 19 6 19H18C18.5523 19 19 18.5523 19 18V8C19 7.44772 18.5523 7 18 7H13H11H6ZM2 10H0V16H2V10ZM22 10H24V16H22V10ZM9 14.5C9.82843 14.5 10.5 13.8284 10.5 13C10.5 12.1716 9.82843 11.5 9 11.5C8.17157 11.5 7.5 12.1716 7.5 13C7.5 13.8284 8.17157 14.5 9 14.5ZM15 14.5C15.8284 14.5 16.5 13.8284 16.5 13C16.5 12.1716 15.8284 11.5 15 11.5C14.1716 11.5 13.5 12.1716 13.5 13C13.5 13.8284 14.1716 14.5 15 14.5Z" />
					</svg>
				</button>
			)}

			{/* Lightbox Preview Modal */}
			{previewImage && (
				<div
					className="fc-lightbox-backdrop"
					onClick={() => setPreviewImage(null)}
				>
					<div
						className="fc-lightbox-card"
						onClick={(e) => e.stopPropagation()}
					>
						<div className="fc-lightbox-header">
							<span className="fc-lightbox-title">{previewImage.alt || "Image Preview"}</span>
							<button
								type="button"
								className="fc-lightbox-close"
								onClick={() => setPreviewImage(null)}
								title="Tutup"
							>
								×
							</button>
						</div>
						<div className="fc-lightbox-body">
							<img
								src={previewImage.src}
								alt={previewImage.alt || "Preview"}
								className="fc-lightbox-img"
							/>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
