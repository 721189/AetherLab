// AetherLab frontend — Next.js Edge middleware.
//
// This is the server-side complement to the client-side <RequireAuth> /
// <RedirectIfAuthed> guards in @/components/auth/guards. Next.js middleware
// runs at the edge (before the route handler) and CANNOT read localStorage,
// so we read an `auth-token` cookie that the Zustand auth store keeps in sync
// with the in-memory access token (see lib/store/authStore.ts).
//
// Auth-model note: the bearer token already lives in localStorage (XSS-surface
// by design in this app). Mirroring it into a non-httpOnly SameSite=Lax cookie
// is therefore not a regression — it is the only way a server-side guard can
// see the session without a backend Set-Cookie, and it keeps dev
// (cross-origin, http) simple. In production, prefer an httpOnly cookie set by
// the backend instead.

import { NextRequest, NextResponse } from "next/server";

/** Cookie name mirrored by the Zustand auth store. */
const AUTH_COOKIE = "auth-token";

/** Auth pages an authenticated user should be bounced away from. */
const UNAUTH_ROUTES = ["/login", "/register"];

/** Public URL prefix for the protected dashboard route group. */
const PROTECTED_PREFIX = "/dashboard";

/** `true` when the request carries a non-empty auth-token cookie. */
function isAuthed(req: NextRequest): boolean {
  return Boolean(req.cookies.get(AUTH_COOKIE)?.value);
}

/** Build a redirect Response to `path`, preserving an optional query string. */
function redirectTo(req: NextRequest, path: string, search = ""): NextResponse {
  const url = req.nextUrl.clone();
  url.pathname = path;
  url.search = search;
  return NextResponse.redirect(url);
}

export function middleware(req: NextRequest): NextResponse {
  const { pathname } = req.nextUrl;

  // Protected dashboard tree — require the auth cookie (presence-only, matching
  // the client guard which also only checks token presence).
  if (pathname.startsWith(PROTECTED_PREFIX)) {
    if (!isAuthed(req)) {
      const callback = `${pathname}${req.nextUrl.search}`;
      return redirectTo(
        req,
        "/login",
        "?callbackUrl=" + encodeURIComponent(callback)
      );
    }
    return NextResponse.next();
  }

  // Authenticated users shouldn't land on the login / register screens.
  if (isAuthed(req) && UNAUTH_ROUTES.some((p) => pathname === p)) {
    return redirectTo(req, "/dashboard");
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register"],
};
