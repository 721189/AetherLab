"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as convApi from "@/lib/api/conversations";
import type { ConversationCreate, Message } from "@/types";

export const convKeys = {
  list: (projectId: number) => ["conversations", projectId] as const,
  detail: (projectId: number, convId: number) =>
    ["conversations", projectId, convId] as const,
  history: (projectId: number, convId: number) =>
    ["conversations", projectId, convId, "messages"] as const,
};

export function useConversations(projectId: number | undefined) {
  return useQuery({
    queryKey: convKeys.list(projectId!),
    queryFn: () => convApi.listConversations(projectId!),
    enabled: projectId != null,
  });
}

export function useCreateConversation(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ConversationCreate) =>
      convApi.createConversation(projectId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: convKeys.list(projectId) }),
  });
}

export function useDeleteConversation(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (convId: number) => convApi.deleteConversation(projectId, convId),
    onSuccess: () => qc.invalidateQueries({ queryKey: convKeys.list(projectId) }),
  });
}

// Optimistically send a message and append the returned exchange.
export function useSendMessage(projectId: number, convId: number) {
  const qc = useQueryClient();
  const historyKey = convKeys.history(projectId, convId);

  return useMutation({
    mutationFn: (content: string) => convApi.sendMessage(projectId, convId, content),
    onMutate: async (content) => {
      await qc.cancelQueries({ queryKey: historyKey });
      const prev = qc.getQueryData<Message[]>(historyKey);
      const optimistic: Message = {
        id: -Date.now(),
        conversation_id: convId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      qc.setQueryData<Message[]>(historyKey, (old) => [
        ...(old ?? []),
        optimistic,
      ]);
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(historyKey, ctx.prev);
    },
    onSuccess: (data) => {
      qc.setQueryData<Message[]>(historyKey, (old) => [
        ...(old ?? []),
        data.user_message,
        data.assistant_message,
      ]);
    },
  });
}