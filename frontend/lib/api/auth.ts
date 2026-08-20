import { apiFetch } from "./client";
import type { Token, User, UserRegisterResponse, VerificationResponse } from "@/types";

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
