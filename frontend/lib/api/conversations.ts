import { apiFetch } from "./client";
import type { Conversation, ConversationCreate, Message, MessageExchange } from "@/types";

export async function listConversations(projectId: number): Promise<Conversation[]> {
  return apiFetch<Conversation[]>(`/api/v1/projects/${projectId}/conversations`);
}

export async function getConversation(
  projectId: number,
  convId: number
): Promise<Conversation> {
  return apiFetch<Conversation>(`/api/v1/projects/${projectId}/conversations/${convId}`);
}

export async function createConversation(
  projectId: number,
  input: ConversationCreate
): Promise<Conversation> {
  return apiFetch<Conversation>(`/api/v1/projects/${projectId}/conversations`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function deleteConversation(
  projectId: number,
  convId: number
): Promise<void> {
  return apiFetch<void>(`/api/v1/projects/${projectId}/conversations/${convId}`, {
    method: "DELETE",
  });
}

export async function sendMessage(
  projectId: number,
  convId: number,
  content: string
): Promise<MessageExchange> {
  return apiFetch<MessageExchange>(
    `/api/v1/projects/${projectId}/conversations/${convId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ content }),
    }
  );
}

// Convenience: the backend persists the exchange but does not return full history.
// We list messages from the returned object only when needed elsewhere.
export type { Message };