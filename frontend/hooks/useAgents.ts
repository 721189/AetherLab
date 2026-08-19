"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as agentsApi from "@/lib/api/agents";
import type { AgentCreateInput, AgentUpdateInput } from "@/types";

export const agentKeys = {
  list: (projectId: number) => ["agents", projectId] as const,
  detail: (projectId: number, agentId: number) =>
    ["agents", projectId, agentId] as const,
};

export function useAgents(projectId: number | undefined) {
  return useQuery({
    queryKey: agentKeys.list(projectId!),
    queryFn: () => agentsApi.listAgents(projectId!),
    enabled: projectId != null,
  });
}

export function useCreateAgent(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: AgentCreateInput) => agentsApi.createAgent(projectId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentKeys.list(projectId) }),
  });
}

export function useUpdateAgent(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, input }: { agentId: number; input: AgentUpdateInput }) =>
      agentsApi.updateAgent(projectId, agentId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentKeys.list(projectId) }),
  });
}

export function useArchiveAgent(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentId: number) => agentsApi.archiveAgent(projectId, agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentKeys.list(projectId) }),
  });
}
