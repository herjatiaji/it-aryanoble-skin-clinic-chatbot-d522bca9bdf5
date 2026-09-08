"use client";

import { useSession } from "@/hooks/use-session";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

interface RouteGuardProps {
	children: React.ReactNode;
	allowedTypes?: Array<"STAFF" | "DOCTOR">;
	requiredAccess?: string;
}

export function RouteGuard({ children, allowedTypes, requiredAccess }: RouteGuardProps) {
	const { user, isLoading, isError } = useSession();
	const router = useRouter();
	const pathname = usePathname();

	useEffect(() => {
		if (isLoading) return;

		if (isError || !user) {
			router.replace(`/login?from=${encodeURIComponent(pathname)}`);
			return;
		}

		if (allowedTypes && !(allowedTypes as string[]).includes(user.type)) {
			if (user.type === "DOCTOR") {
				router.replace("/doctor");
			} else {
				router.replace("/dashboard/knowledge");
			}
			return;
		}

		if (requiredAccess && user.type === "STAFF") {
			const userAccesses = user.accesses || [];
			if (!userAccesses.includes(requiredAccess)) {
				router.replace("/dashboard/knowledge");
			}
		}
	}, [user, isLoading, isError, router, pathname, allowedTypes, requiredAccess]);

	if (isLoading) {
		return (
			<div className="flex h-screen w-full items-center justify-center bg-background">
				<div className="flex flex-col items-center gap-2">
					<div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
					<p className="text-sm text-muted-foreground">Authenticating session...</p>
				</div>
			</div>
		);
	}

	if (!user) {
		return null;
	}

	return <>{children}</>;
}
