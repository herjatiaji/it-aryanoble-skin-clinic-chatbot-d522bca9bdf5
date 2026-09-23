"use client";

import { authKeys } from "@/app/login/api/keys";
import { IdleTimeoutDialog } from "@/components/auth";
import { api } from "@/lib/axios";
import type { UserResponse } from "@/lib/types";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import React, { createContext, useCallback, useContext } from "react";
import { useCurrentUser } from "./use-current-user";
import { useIdleTimer } from "./use-idle-timer";

interface AuthContextType {
	user: UserResponse | null;
	isLoading: boolean;
	isError: boolean;
}

const AuthContext = createContext<AuthContextType>({
	user: null,
	isLoading: true,
	isError: false,
});

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
	const { data: user, isLoading, isError } = useCurrentUser();
	const queryClient = useQueryClient();
	const router = useRouter();

	const handleLogout = useCallback(
		async (reason: "idle" | "manual" = "manual") => {
			try {
				await api.post("/auth/logout");
			} catch {
				// Ignore network errors during logout
			} finally {
				if (typeof window !== "undefined") {
					try {
						localStorage.removeItem("arya_noble_last_active");
					} catch {}
				}
				queryClient.removeQueries({ queryKey: authKeys.all });
				if (typeof window !== "undefined") {
					const query = reason === "idle" ? "?reason=idle" : "";
					router.push(`/login${query}`);
				}
			}
		},
		[queryClient, router],
	);

	const handleStayLoggedIn = useCallback(async () => {
		try {
			await api.post("/auth/refresh");
		} catch {}
	}, []);

	const { isWarning, remainingSeconds, resetTimer } = useIdleTimer({
		idleTimeoutMs: 15 * 60 * 1000,
		warningTimeoutMs: 60 * 1000,
		enabled: !!user,
		onIdleTimeout: () => {
			handleLogout("idle");
		},
	});

	const onStayLoggedInClick = () => {
		resetTimer();
		handleStayLoggedIn();
	};

	const onLogoutNowClick = () => {
		handleLogout("manual");
	};

	return (
		<AuthContext.Provider value={{ user: user || null, isLoading, isError }}>
			{children}
			{user && (
				<IdleTimeoutDialog
					open={isWarning}
					remainingSeconds={remainingSeconds}
					onStayLoggedIn={onStayLoggedInClick}
					onLogoutNow={onLogoutNowClick}
				/>
			)}
		</AuthContext.Provider>
	);
};

export const useSession = () => {
	const context = useContext(AuthContext);
	if (context === undefined) {
		throw new Error("useSession must be used within an AuthProvider");
	}
	return context;
};
