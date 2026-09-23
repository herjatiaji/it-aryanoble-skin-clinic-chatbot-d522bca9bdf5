"use client";

import {
	MessageScroller,
	MessageScrollerContent,
	MessageScrollerProvider,
	MessageScrollerSmartButton,
	MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { useChatMessages } from "@/hooks/use-chat-messages";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useSafeBack } from "@/hooks/use-safe-back";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useChatHistoryDetail } from "../hooks/use-chat-history";
import { ChatDetailEmptyState } from "./components/chat-detail-empty-state";
import { ChatDetailHeader } from "./components/chat-detail-header";
import { ChatDetailMessageItem } from "./components/chat-detail-message-item";
import { ChatDetailSkeleton } from "./components/skeletons/chat-detail-skeleton";

export default function ChatHistoryDetailPage() {
	const params = useParams();
	const router = useRouter();
	const handleBack = useSafeBack("/dashboard/chat-history");
	const sessionId = params.id as string;

	const { data: currentUser } = useCurrentUser();
	const { data: session } = useChatHistoryDetail(sessionId);
	const { data: messages, isLoading } = useChatMessages(sessionId);

	const isOwner = Boolean(
		currentUser?.id && session?.user_id && currentUser.id === session.user_id,
	);
	const isStaffOrAdmin = currentUser?.type === "STAFF" || currentUser?.type === "ADMIN";
	const isGeneralChat =
		session?.session_type === "GENERAL_ASSISTANT" ||
		(!session?.branch_id && session?.branch === "General Assistant") ||
		session?.user_type === "STAFF";

	useEffect(() => {
		if (isOwner && isStaffOrAdmin && isGeneralChat && sessionId) {
			router.replace(`/dashboard/ingest/chat?session_id=${sessionId}`);
		}
	}, [isOwner, isStaffOrAdmin, isGeneralChat, sessionId, router]);

	const sessionTitle = session?.user_name || session?.doctor || "Chat Session Details";

	const handleContinueChat = () => {
		router.push(`/dashboard/ingest/chat?session_id=${sessionId}`);
	};

	return (
		<div className="flex flex-col absolute inset-0 bg-white overflow-hidden">
			{/* Header */}
			<ChatDetailHeader
				sessionTitle={sessionTitle}
				session={session}
				isOwner={isOwner}
				isStaffOrAdmin={isStaffOrAdmin}
				isGeneralChat={isGeneralChat}
				sessionId={sessionId}
				onBack={handleBack}
				onContinueChat={handleContinueChat}
			/>

			{/* Main Chat Area */}
			<div className="flex flex-1 overflow-hidden min-h-0">
				<div className="flex flex-col flex-1 bg-white overflow-hidden min-h-0 h-full">
					<MessageScrollerProvider>
						<MessageScroller className="flex-1 min-h-0">
							<MessageScrollerViewport className="px-6 sm:px-8">
								<MessageScrollerContent className="py-8 gap-6 w-full max-w-5xl mx-auto min-w-0">
									{isLoading && <ChatDetailSkeleton />}

									{!isLoading && (!messages || messages.length === 0) && <ChatDetailEmptyState />}

									{!isLoading &&
										messages?.map((msg, index) => (
											<ChatDetailMessageItem
												key={msg.id || `msg-${index}`}
												message={msg}
												isLast={index === messages.length - 1}
												index={index}
											/>
										))}
								</MessageScrollerContent>
							</MessageScrollerViewport>
							<MessageScrollerSmartButton />
						</MessageScroller>
					</MessageScrollerProvider>
				</div>
			</div>
		</div>
	);
}
