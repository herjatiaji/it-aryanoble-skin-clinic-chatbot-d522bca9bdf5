import {
	useCreateGeneralChatSession,
	useGeneralChatSession,
} from "@/app/dashboard/knowledge/hooks/use-knowledge";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export function useGeneralChatState() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const sessionId = searchParams.get("session_id");
	const initialPrompt = searchParams.get("q") || searchParams.get("initialPrompt") || "";
	const [sessionKey, setSessionKey] = useState(0);

	const createSession = useCreateGeneralChatSession();
	const { isError: isSessionError } = useGeneralChatSession(sessionId);
	const isInitializingRef = useRef(false);

	useEffect(() => {
		// If user visits /dashboard/ingest/chat directly without a session_id, or with an invalid/unauthorized session_id, create a new one
		if ((!sessionId || isSessionError) && !isInitializingRef.current) {
			isInitializingRef.current = true;
			const initSession = async () => {
				try {
					const newSession = await createSession.mutateAsync();
					if (initialPrompt) {
						router.replace(
							`/dashboard/ingest/chat?session_id=${newSession.id}&q=${encodeURIComponent(initialPrompt)}`,
						);
					} else {
						router.replace(`/dashboard/ingest/chat?session_id=${newSession.id}`);
					}
				} catch {
					// Silent fail
				} finally {
					isInitializingRef.current = false;
				}
			};
			void initSession();
		}
	}, [sessionId, isSessionError, initialPrompt, createSession, router]);

	const handleNewSession = async () => {
		try {
			const newSession = await createSession.mutateAsync();
			setSessionKey((prev) => prev + 1);
			router.replace(`/dashboard/ingest/chat?session_id=${newSession.id}`);
		} catch {
			setSessionKey((prev) => prev + 1);
			router.replace("/dashboard/ingest/chat");
		}
	};

	return {
		sessionId,
		initialPrompt,
		sessionKey,
		isCreatingSession: createSession.isPending,
		handleNewSession,
	};
}
