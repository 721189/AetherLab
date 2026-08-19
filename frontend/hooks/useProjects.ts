"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as projectsApi from "@/lib/api/projects";
import type { Project, ProjectInput } from "@/types";

export const projectKeys = {
  all: ["projects"] as const,
  detail: (id: number) => ["projects", id] as const,
};

export function useProjects() {
  return useQuery({
    queryKey: projectKeys.all,
    queryFn: projectsApi.listProjects,
  });
}

export function useProject(id: number | undefined) {
  return useQuery({
    queryKey: projectKeys.detail(id!),
    queryFn: () => projectsApi.getProject(id!),
    enabled: id != null,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectInput) => projectsApi.createProject(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<ProjectInput> & { is_archived?: boolean } }) =>
      projectsApi.updateProject(id, input),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: projectKeys.all });
      qc.invalidateQueries({ queryKey: projectKeys.detail(vars.id) });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => projectsApi.deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}
