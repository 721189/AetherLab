"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
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
  const setAuth = useAuth((s) => s.setAuth);

  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.register({ email, password }),
    onSuccess: async (user, variables) => {
      // The backend returns the user but not a token, so immediately log in.
      const token = await authApi.login({
        email: variables.email,
        password: variables.password,
      });
      setAuth(token, user);
      router.push("/dashboard");
    },
  });
}
