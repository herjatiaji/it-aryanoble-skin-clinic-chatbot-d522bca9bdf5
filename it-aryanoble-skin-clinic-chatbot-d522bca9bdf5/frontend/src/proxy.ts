import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

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
    const padded = base64.padEnd(base64.length + (4 - (base64.length % 4)) % 4, "=");
    const jsonPayload = atob(padded);
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("access_token")?.value;
  const payload = token ? parseJwt(token) : null;
  const isExpired = payload?.exp ? payload.exp * 1000 < Date.now() : true;
  const isAuthenticated = payload && !isExpired;

  // Determine home landing page based on role
  let homePath = "/login";
  if (isAuthenticated && payload) {
    if (payload.type === "DOCTOR") {
      homePath = "/doctor";
    } else if (payload.type === "STAFF") {
      homePath = "/dashboard/knowledge";
    }
  }

  // Handle /login page for authenticated users
  if (pathname === "/login") {
    if (isAuthenticated) {
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
    if (!isAuthenticated) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("from", pathname);
      return NextResponse.redirect(loginUrl);
    }
    if (payload?.type !== "STAFF") {
      return NextResponse.redirect(new URL("/doctor", request.url));
    }
    
    // We could do granular route checking here if we want,
    // e.g., if (pathname.startsWith("/dashboard/users") && !payload.accesses.includes("users:read"))
    // but the backend API protects the data, and the sidebar won't show the links.
    // For now, allow navigation to /dashboard/* and rely on backend 403s for protection.
    
    return NextResponse.next();
  }

  // Handle /doctor routes
  if (pathname.startsWith("/doctor")) {
    if (!isAuthenticated) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("from", pathname);
      return NextResponse.redirect(loginUrl);
    }
    if (payload?.type !== "DOCTOR") {
      return NextResponse.redirect(new URL(homePath, request.url));
    }
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/functional/:path*", "/dashboard/:path*", "/doctor/:path*", "/login"],
};
