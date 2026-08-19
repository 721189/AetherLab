import { apiFetch } from "./client";
import type { Token, User } from "@/types";

export interface LoginPayload {
  email: string;
  password: string;
}

export async function login(payload: LoginPayload): Promise<Token> {
  return apiFetch<Token>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  }, false);
}

export async function register(payload: LoginPayload): Promise<User> {
  return apiFetch<User>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  }, false);
}

export async function me(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me");
}
