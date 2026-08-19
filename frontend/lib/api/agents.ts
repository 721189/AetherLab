import { apiFetch } from "./client";
import type { Agent, AgentCreateInput, AgentUpdateInput } from "@/types";

export async function listAgents(projectId: number): Promise<Agent[]> {
  return apiFetch<Agent[]>(`/api/v1/projects/${projectId}/agents`);
}

export async function getAgent(
  projectId: number,
  agentId: number
): Promise<Agent> {
  return apiFetch<Agent>(`/api/v1/projects/${projectId}/agents/${agentId}`);
}

export async function createAgent(
  projectId: number,
  input: AgentCreateInput
): Promise<Agent> {
  return apiFetch<Agent>(`/api/v1/projects/${projectId}/agents`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateAgent(
  projectId: number,
  agentId: number,
  input: AgentUpdateInput
): Promise<Agent> {
  return apiFetch<Agent>(`/api/v1/projects/${projectId}/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function archiveAgent(
  projectId: number,
  agentId: number
): Promise<void> {
  return apiFetch<void>(`/api/v1/projects/${projectId}/agents/${agentId}`, {
    method: "DELETE",
  });
}