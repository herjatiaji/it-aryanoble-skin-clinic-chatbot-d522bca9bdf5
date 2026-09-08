import { useState, useEffect, useRef } from "react";
import "./FloatingChatbot.css";

/**
 * FloatingChatbot Component
 *
 * A reference implementation for integrating the Arya Noble AI Chatbot into a React application.
 *
 * @param {Object} props
 * @param {string} props.token - The JWT token provided by the CIS system (used for authorization).
 * @param {string} props.doctorName - The name of the doctor currently logged in (for display).
 * @param {string} props.branchId - The UUID of the branch the doctor is currently operating in.
 * @param {string} [props.apiBaseUrl] - The base URL of the Chatbot API (e.g., https://api.arya-noble.com).
 */
export default function FloatingChatbot({
	token,
	doctorName = "Doctor",
	branchId,
	apiBaseUrl = "http://localhost:8000",
}) {
	const [isOpen, setIsOpen] = useState(false);
	const [messages, setMessages] = useState([]);
	const [input, setInput] = useState("");
	const [sessionId, setSessionId] = useState(null);
	const [isLoading, setIsLoading] = useState(false);
	const chatEndRef = useRef(null);

	useEffect(() => {
		chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages]);

	const toggleChat = async () => {
		const nextState = !isOpen;
		setIsOpen(nextState);

		// Step 1: If opening for the first time, create a new chat session via the API
		if (nextState && !sessionId && token) {
			try {
				const res = await fetch(`${apiBaseUrl}/api/chats/`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Authorization: `Bearer ${token}`, // Use the seamless SSO token
					},
					body: JSON.stringify({
						branch_id: branchId,
					}),
				});
				if (res.ok) {
					const data = await res.json();
					setSessionId(data.id);
					setMessages([
						{ id: "init", role: "assistant", content: "Your artificial intelligence assistant" },
					]);
				}
			} catch (err) {
				console.error("Failed to create session:", err);
			}
		}
	};

	const handleSend = async (e) => {
		e.preventDefault();
		if (!input.trim() || !sessionId || !token || isLoading) return;

		const userMessage = { id: Date.now().toString(), role: "user", content: input };
		setMessages((prev) => [...prev, userMessage]);
		setInput("");
		setIsLoading(true);

		try {
			// Step 2: Send the user's message using FormData (supports file attachments if needed)
			const formData = new FormData();
			formData.append("role", "user");
			formData.append("content", userMessage.content);

			const res = await fetch(`${apiBaseUrl}/api/chats/${sessionId}/messages`, {
				method: "POST",
				headers: {
					Authorization: `Bearer ${token}`,
				},
				body: formData,
			});

			if (res.ok) {
				// Step 3: Poll the API to retrieve the AI's response
				// Note: In production, consider implementing WebSockets or Server-Sent Events (SSE)
				// for real-time updates instead of polling, if supported by the backend.
				setTimeout(async () => {
					const histRes = await fetch(`${apiBaseUrl}/api/chats/${sessionId}/messages`, {
						headers: { Authorization: `Bearer ${token}` },
					});
					if (histRes.ok) {
						const histData = await histRes.json();
						setMessages(histData);
					}
					setIsLoading(false);
				}, 3000);
			} else {
				setIsLoading(false);
			}
		} catch (err) {
			console.error(err);
			setIsLoading(false);
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
							<h3>Erha AI</h3>
							<span>Assisting {doctorName}</span>
						</div>
					</div>
					<div className="fc-header-actions">
						<button className="fc-action-btn">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="currentColor"
								width="20"
								height="20"
							>
								<path d="M16.004 9.414l-8.607 8.607-1.414-1.414L14.59 8H7.004V6h11v11h-2V9.414z" />
							</svg>
						</button>
						<button onClick={() => setIsOpen(false)} className="fc-action-btn">
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

				{/* Content Area */}
				<div className="fc-body">
					{messages.map((msg) => (
						<div
							key={msg.id}
							className={`fc-message-row ${msg.role === "user" ? "fc-row-user" : "fc-row-assistant"}`}
						>
							<div className={`fc-bubble ${msg.role === "user" ? "fc-user" : "fc-assistant"}`}>
								{msg.content}
							</div>
						</div>
					))}
					{isLoading && (
						<div className="fc-message-row fc-row-assistant">
							<div className="fc-bubble fc-assistant fc-loading">
								<span className="fc-dot"></span>
								<span className="fc-dot"></span>
								<span className="fc-dot"></span>
							</div>
						</div>
					)}
					<div ref={chatEndRef} />
				</div>

				{/* Input Area */}
				<div className="fc-footer">
					<form onSubmit={handleSend} className="fc-input-wrapper">
						<input
							type="text"
							value={input}
							onChange={(e) => setInput(e.target.value)}
							placeholder="Describe what your concern is..."
							disabled={isLoading || !sessionId}
						/>
						<button type="submit" disabled={isLoading || !input.trim() || !sessionId}>
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
					</form>
				</div>
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
		</div>
	);
}
