import { apiFetch } from "./client";
import type { Token, User, UserRegisterResponse, VerificationResponse } from "@/types";

export interface LoginPayload {
  email: string;
  password: string;
}

export async function login(payload: LoginPayload): Promise<Token> {
  // Non-browser clients use this endpoint (tokens in the JSON body).
  return apiFetch<Token>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  }, false);
}

export interface BrowserLoginResponse {
  message: string;
}

export async function loginBrowser(
  payload: LoginPayload
): Promise<BrowserLoginResponse> {
  // Browser sessions authenticate via HttpOnly cookies ONLY — the response
  // contains no tokens for JavaScript to read or persist.
  return apiFetch<BrowserLoginResponse>("/api/v1/auth/login/browser", {
    method: "POST",
    body: JSON.stringify(payload),
  }, false);
}

export interface RegisterPayload {
  email: string;
  password: string;
}

export async function register(
  payload: RegisterPayload
): Promise<UserRegisterResponse> {
  return apiFetch<UserRegisterResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  }, false);
}

export async function verifyEmail(token: string): Promise<VerificationResponse> {
  return apiFetch<VerificationResponse>(`/api/v1/auth/verify/${encodeURIComponent(token)}`);
}

export interface ResendVerificationPayload {
  email: string;
}

export async function resendVerification(
  payload: ResendVerificationPayload
): Promise<VerificationResponse> {
  return apiFetch<VerificationResponse>("/api/v1/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function me(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me");
}

export async function logout(): Promise<{ message: string }> {
  // Expires the HttpOnly cookies server-side; the JSON body is informational.
  return apiFetch<{ message: string }>("/api/v1/auth/logout", {
    method: "POST",
  }, false);
}
