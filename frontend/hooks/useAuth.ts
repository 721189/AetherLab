"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import * as authApi from "@/lib/api/auth";
import { useAuth } from "@/lib/store/authStore";

export const authKeys = {
  me: ["auth", "me"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: authApi.me,
    enabled: false, // opt-in; called explicitly after login/hydration
    retry: false,
  });
}

export function useLogin() {
  const router = useRouter();
  const qc = useQueryClient();
  const setAuth = useAuth((s) => s.setAuth);

  return useMutation({
    mutationFn: authApi.login,
    onSuccess: async (token) => {
      const user = await authApi.me();
      setAuth(token, user);
      qc.setQueryData(authKeys.me, user);
      router.push("/dashboard");
    },
  });
}

export function useRegister() {
  const router = useRouter();

  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.register({ email, password }),
    onSuccess: () => {
      // The verification link arrives by email; there is no auto-verify step.
      toast.success(
        "Account created — check your inbox to verify your email before signing in."
      );
      router.push("/login");
    },
  });
}
