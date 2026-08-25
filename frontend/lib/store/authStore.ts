"use client";

import { create } from "zustand";
import type { Token, User } from "@/types";

interface AuthState {
  accessToken: string | null;
  user: User | null;
  setAuth: (token: Token, user: User) => void;
  setUser: (user: User) => void;
  logout: () => void;
}

/**
 * Auth model (HttpOnly-cookie based):
 *
 * The backend sets HttpOnly Secure SameSite=Lax cookies at /auth/login, so
 * the browser holds the session secret where JavaScript CANNOT read it
 * (`document.cookie` does not expose it). This store therefore persists ONLY
 * non-secret state (the user profile); the access token is kept in memory for
 * the lifetime of the tab and never written to localStorage or a JS-readable
 * cookie.
 */
export const useAuth = create<AuthState>()((set) => ({
  accessToken: null,
  user: null,
  setAuth: (token, user) => set({ accessToken: token.access_token, user }),
  setUser: (user) => set({ user }),
  logout: () => set({ accessToken: null, user: null }),
}));

// Synchronous accessors kept for backwards compatibility. The token is
// memory-only now; cookie-based requests are handled by the API client via
// `credentials: "include"`.
export function getAccessToken(): string | null {
  return useAuth.getState().accessToken;
}

export function isAuthenticated(): boolean {
  const { accessToken, user } = useAuth.getState();
  return Boolean(accessToken || user);
}

