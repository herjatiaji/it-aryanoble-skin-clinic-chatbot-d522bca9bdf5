"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "arya_noble_last_active";
const THROTTLE_MS = 2000; // Throttle storage writes to once every 2s

export interface UseIdleTimerOptions {
	/**
	 * Time in ms before the idle warning is triggered.
	 * Default: 15 minutes (900,000 ms).
	 */
	idleTimeoutMs?: number;
	/**
	 * Duration in ms for the warning countdown before auto-logout occurs.
	 * Default: 60 seconds (60,000 ms).
	 */
	warningTimeoutMs?: number;
	onIdleWarning?: () => void;
	onIdleTimeout?: () => void;
	onActive?: () => void;
	enabled?: boolean;
}

export function useIdleTimer({
	idleTimeoutMs = 15 * 60 * 1000,
	warningTimeoutMs = 60 * 1000,
	onIdleWarning,
	onIdleTimeout,
	onActive,
	enabled = true,
}: UseIdleTimerOptions = {}) {
	const [isWarning, setIsWarning] = useState(false);
	const [remainingSeconds, setRemainingSeconds] = useState(Math.ceil(warningTimeoutMs / 1000));

	const lastRecordedTimeRef = useRef<number>(0);
	const lastThrottleRef = useRef<number>(0);
	const checkIntervalRef = useRef<NodeJS.Timeout | null>(null);

	// Keep fresh references to callbacks without re-attaching listeners
	const onIdleWarningRef = useRef(onIdleWarning);
	const onIdleTimeoutRef = useRef(onIdleTimeout);
	const onActiveRef = useRef(onActive);
	const isWarningRef = useRef(isWarning);

	useEffect(() => {
		onIdleWarningRef.current = onIdleWarning;
		onIdleTimeoutRef.current = onIdleTimeout;
		onActiveRef.current = onActive;
		isWarningRef.current = isWarning;
	});

	// Synchronize activity across all tabs
	const recordActivity = useCallback(() => {
		const now = Date.now();
		lastRecordedTimeRef.current = now;

		if (now - lastThrottleRef.current > THROTTLE_MS) {
			lastThrottleRef.current = now;
			try {
				localStorage.setItem(STORAGE_KEY, now.toString());
			} catch {
				// Fallback for private browsing or restricted environments
			}
		}

		if (isWarningRef.current) {
			setIsWarning(false);
			onActiveRef.current?.();
		}
	}, []);

	const resetTimer = useCallback(() => {
		const now = Date.now();
		lastRecordedTimeRef.current = now;
		try {
			localStorage.setItem(STORAGE_KEY, now.toString());
		} catch {
			// Fallback
		}
		setIsWarning(false);
		setRemainingSeconds(Math.ceil(warningTimeoutMs / 1000));
		onActiveRef.current?.();
	}, [warningTimeoutMs]);

	// Listen to cross-tab storage changes
	useEffect(() => {
		if (!enabled) return;

		const handleStorageChange = (e: StorageEvent) => {
			if (e.key === STORAGE_KEY && e.newValue) {
				const remoteTime = parseInt(e.newValue, 10);
				if (!isNaN(remoteTime)) {
					lastRecordedTimeRef.current = remoteTime;
					if (isWarningRef.current) {
						setIsWarning(false);
						onActiveRef.current?.();
					}
				}
			}
		};

		window.addEventListener("storage", handleStorageChange);
		return () => window.removeEventListener("storage", handleStorageChange);
	}, [enabled]);

	// Set up user interaction listeners
	useEffect(() => {
		if (!enabled) return;

		const inputEvents = [
			"mousemove",
			"mousedown",
			"keydown",
			"touchstart",
			"scroll",
		];

		const handleUserActivity = () => {
			if (!isWarningRef.current) {
				recordActivity();
			}
		};

		// Tab visibility check: verify timeout if returning after being away
		const handleVisibilityChange = () => {
			if (document.visibilityState === "visible") {
				const now = Date.now();
				let lastActive = lastRecordedTimeRef.current;
				try {
					const stored = localStorage.getItem(STORAGE_KEY);
					if (stored) {
						const parsed = parseInt(stored, 10);
						if (!isNaN(parsed)) {
							lastActive = Math.max(lastActive, parsed);
							lastRecordedTimeRef.current = lastActive;
						}
					}
				} catch {
					// Ignore
				}

				const elapsed = now - lastActive;
				const totalTimeout = idleTimeoutMs + warningTimeoutMs;

				if (elapsed >= totalTimeout) {
					setIsWarning(false);
					onIdleTimeoutRef.current?.();
				}
			}
		};

		inputEvents.forEach((evt) => {
			window.addEventListener(evt, handleUserActivity, { passive: true });
		});
		document.addEventListener("visibilitychange", handleVisibilityChange);

		return () => {
			inputEvents.forEach((evt) => {
				window.removeEventListener(evt, handleUserActivity);
			});
			document.removeEventListener("visibilitychange", handleVisibilityChange);
		};
	}, [enabled, idleTimeoutMs, warningTimeoutMs, recordActivity]);

	// Periodic interval to check idle duration
	useEffect(() => {
		if (!enabled) return;

		const totalTimeout = idleTimeoutMs + warningTimeoutMs;
		const now = Date.now();

		try {
			const stored = localStorage.getItem(STORAGE_KEY);
			if (stored) {
				const parsed = parseInt(stored, 10);
				// Only use stored timestamp if it is valid and from the recent active window
				if (!isNaN(parsed) && (now - parsed) < totalTimeout) {
					lastRecordedTimeRef.current = parsed;
				} else {
					// Stale or expired past session timestamp: reset to now
					lastRecordedTimeRef.current = now;
					localStorage.setItem(STORAGE_KEY, now.toString());
				}
			} else {
				lastRecordedTimeRef.current = now;
				localStorage.setItem(STORAGE_KEY, now.toString());
			}
		} catch {
			lastRecordedTimeRef.current = Date.now();
		}

		checkIntervalRef.current = setInterval(() => {
			const currentTime = Date.now();
			let lastActive = lastRecordedTimeRef.current;

			try {
				const stored = localStorage.getItem(STORAGE_KEY);
				if (stored) {
					const parsed = parseInt(stored, 10);
					if (!isNaN(parsed)) {
						lastActive = Math.max(lastActive, parsed);
						lastRecordedTimeRef.current = lastActive;
					}
				}
			} catch {
				// Ignore
			}

			const elapsed = currentTime - lastActive;

			if (elapsed >= totalTimeout) {
				setIsWarning(false);
				if (checkIntervalRef.current) clearInterval(checkIntervalRef.current);
				onIdleTimeoutRef.current?.();
			} else if (elapsed >= idleTimeoutMs) {
				if (!isWarningRef.current) {
					setIsWarning(true);
					onIdleWarningRef.current?.();
				}
				const remainingMs = Math.max(0, totalTimeout - elapsed);
				setRemainingSeconds(Math.ceil(remainingMs / 1000));
			} else {
				if (isWarningRef.current) {
					setIsWarning(false);
				}
			}
		}, 1000);

		return () => {
			if (checkIntervalRef.current) {
				clearInterval(checkIntervalRef.current);
			}
		};
	}, [enabled, idleTimeoutMs, warningTimeoutMs]);

	return {
		isWarning,
		remainingSeconds,
		resetTimer,
	};
}
