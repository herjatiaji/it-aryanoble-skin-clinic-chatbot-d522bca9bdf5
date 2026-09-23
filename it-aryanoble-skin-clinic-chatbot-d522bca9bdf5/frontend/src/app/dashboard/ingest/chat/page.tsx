"use client";

import { ChatPreview } from "@/app/dashboard/knowledge/components/preview/chat-preview";
import { Suspense } from "react";
import { ChatHeader } from "./components/chat-header";
import { ChatSessionSkeleton } from "./components/skeletons/chat-session-skeleton";
import { useGeneralChatState } from "./hooks/use-general-chat-state";

function GeneralChatContent() {
	const { sessionId, initialPrompt, sessionKey, isCreatingSession, handleNewSession } =
		useGeneralChatState();

	return (
		<div className="flex flex-col absolute inset-0">
			<ChatHeader isCreatingSession={isCreatingSession} onNewSession={handleNewSession} />

			<div className="flex flex-1 overflow-hidden">
				<ChatPreview
					key={`${sessionId || "new"}_${sessionKey}`}
					mode="general"
					sessionId={sessionId}
					initialPrompt={initialPrompt}
				/>
			</div>
		</div>
	);
}

export default function GeneralChatPage() {
	return (
		<Suspense fallback={<ChatSessionSkeleton />}>
			<GeneralChatContent />
		</Suspense>
	);
}
