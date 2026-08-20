"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Token, User } from "@/types";

interface AuthState {
  accessToken: string | null;
  user: User | null;
  setAuth: (token: Token, user: User) => void;
  setUser: (user: User) => void;
  logout: () => void;
}

/**
 * Name of the cookie that mirrors the access token so that Next.js Edge
 * middleware (frontend/middleware.ts) — which cannot read `localStorage` — can
 * perform server-side route protection. Kept in sync in setAuth / logout below.
 */
const AUTH_COOKIE = "auth-token";
const COOKIE_MAX_AGE = 60 * 30; // 30 min — mirrors the backend JWT TTL (env: ACCESS_TOKEN_EXPIRE_MINUTES)

function setAuthCookie(token: string): void {
  if (typeof document === "undefined") return; // no-op during SSR/static generation
  document.cookie = `${AUTH_COOKIE}=${token}; Path=/; Max-Age=${COOKIE_MAX_AGE}; SameSite=Lax`;
}

function clearAuthCookie(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${AUTH_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      user: null,
      setAuth: (token, user) => {
        setAuthCookie(token.access_token);
        set({ accessToken: token.access_token, user });
      },
      setUser: (user) => set({ user }),
      logout: () => {
        clearAuthCookie();
        set({ accessToken: null, user: null });
      },
    }),
    {
      name: "aetherlab-auth",
    }
  )
);

// Synchronous token access for the API client (no hook needed).
export function getAccessToken(): string | null {
  return useAuth.getState().accessToken;
}

export function isAuthenticated(): boolean {
  return Boolean(useAuth.getState().accessToken);
}
