"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";

/**
 * Custom hook for resilient back navigation.
 * Uses `router.back()` when valid in-app history exists,
 * otherwise safely routes to `fallbackUrl` (preventing stuck states on fresh tabs / direct URLs).
 */
export function useSafeBack(fallbackUrl: string) {
	const router = useRouter();

	const handleBack = useCallback(() => {
		if (typeof window !== "undefined") {
			const hasHistory = window.history.length > 1;
			const isSameOriginReferrer =
				Boolean(document.referrer) &&
				document.referrer.startsWith(window.location.origin);

			if (hasHistory && (isSameOriginReferrer || !document.referrer)) {
				router.back();
				return;
			}
		}

		router.push(fallbackUrl);
	}, [router, fallbackUrl]);

	return handleBack;
}
