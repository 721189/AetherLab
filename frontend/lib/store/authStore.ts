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

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      user: null,
      setAuth: (token, user) => set({ accessToken: token.access_token, user }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, user: null }),
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