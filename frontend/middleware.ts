// AetherLab frontend — Next.js Edge middleware.
//
// Route protection is NOT inferred from the mere presence of a cookie —
// `access_token=anything` must not make the frontend believe a user is signed
// in. Instead the backend remains authoritative:
//
//     Next middleware -> forward cookies to GET /auth/me -> real validation
//
// The check is deliberately lightweight (one fetch); heavy authorization
// always happens in the API itself.

import { NextRequest, NextResponse } from "next/server";

/** Auth pages an authenticated user should be bounced away from. */
const UNAUTH_ROUTES = ["/login", "/register"];

/** Public URL prefix for the protected dashboard route group. */
const PROTECTED_PREFIX = "/dashboard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/**
 * Ask the backend whether this request's session cookies represent a valid,
 * authenticated session. Returns false on any failure (network down, invalid
 * or expired token) — fail closed.
 */
async function isAuthenticated(req: NextRequest): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/me`, {
      headers: { cookie: req.headers.get("cookie") ?? "" },
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false; // backend unreachable -> treat as unauthenticated
  }
}

/** Build a redirect Response to `path`, preserving an optional query string. */
function redirectTo(req: NextRequest, path: string, search = ""): NextResponse {
  const url = req.nextUrl.clone();
  url.pathname = path;
  url.search = search;
  return NextResponse.redirect(url);
}

export async function middleware(req: NextRequest): Promise<NextResponse> {
  const { pathname } = req.nextUrl;

  // Protected dashboard tree — validated against the backend session store.
  if (pathname.startsWith(PROTECTED_PREFIX)) {
    if (!(await isAuthenticated(req))) {
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
  if (
    UNAUTH_ROUTES.some((p) => pathname === p) &&
    (await isAuthenticated(req))
  ) {
    return redirectTo(req, "/dashboard");
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register"],
};
