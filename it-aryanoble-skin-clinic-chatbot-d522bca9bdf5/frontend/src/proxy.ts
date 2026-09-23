import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

interface JwtPayload {
	sub?: string;
	type?: "STAFF" | "DOCTOR";
	roles?: string[];
	accesses?: string[];
	exp?: number;
}

function parseJwt(token: string): JwtPayload | null {
	try {
		const base64Url = token.split(".")[1];
		if (!base64Url) return null;
		const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
		const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
		const jsonPayload = atob(padded);
		return JSON.parse(jsonPayload);
	} catch {
		return null;
	}
}

export function proxy(request: NextRequest) {
	const { pathname } = request.nextUrl;
	const accessToken = request.cookies.get("access_token")?.value;
	const refreshToken = request.cookies.get("refresh_token")?.value;

	const accessPayload = accessToken ? parseJwt(accessToken) : null;
	const refreshPayload = refreshToken ? parseJwt(refreshToken) : null;

	const isAccessExpired = accessPayload?.exp ? accessPayload.exp * 1000 < Date.now() : true;
	const isRefreshExpired = refreshPayload?.exp ? refreshPayload.exp * 1000 < Date.now() : true;

	const hasActiveSession = (accessPayload && !isAccessExpired) || (refreshPayload && !isRefreshExpired);

	// Determine home landing page based on role
	let homePath = "/login";
	if (accessPayload && !isAccessExpired && accessPayload.type === "STAFF") {
		homePath = "/dashboard/knowledge";
	}

	// Handle /login page for authenticated users with active access token
	if (pathname === "/login") {
		if (accessPayload && !isAccessExpired) {
			return NextResponse.redirect(new URL(homePath, request.url));
		}
		return NextResponse.next();
	}

	// Redirect old /admin and /functional to /dashboard
	if (pathname.startsWith("/admin") || pathname.startsWith("/functional")) {
		const newPath = pathname.replace(/^\/(admin|functional)/, "/dashboard");
		return NextResponse.redirect(new URL(newPath, request.url));
	}

	// Handle /dashboard routes
	if (pathname.startsWith("/dashboard")) {
		if (!hasActiveSession) {
			const loginUrl = new URL("/login", request.url);
			loginUrl.searchParams.set("reason", "session_expired");
			loginUrl.searchParams.set("from", pathname);
			return NextResponse.redirect(loginUrl);
		}
		if (accessPayload && !isAccessExpired && accessPayload.type !== "STAFF") {
			return NextResponse.redirect(new URL("/login", request.url));
		}

		// We could do granular route checking here if we want,
		// e.g., if (pathname.startsWith("/dashboard/users") && !payload.accesses.includes("users:read"))
		// but the backend API protects the data, and the sidebar won't show the links.
		// For now, allow navigation to /dashboard/* and rely on backend 403s for protection.

		return NextResponse.next();
	}

	return NextResponse.next();
}

export const config = {
	matcher: ["/admin/:path*", "/functional/:path*", "/dashboard/:path*", "/login"],
};
