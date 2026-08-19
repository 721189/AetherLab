import { apiFetch } from "./client";
import type { Project, ProjectInput } from "@/types";

export async function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/api/v1/projects");
}

export async function getProject(id: number): Promise<Project> {
  return apiFetch<Project>(`/api/v1/projects/${id}`);
}

export async function createProject(input: ProjectInput): Promise<Project> {
  return apiFetch<Project>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateProject(
  id: number,
  input: Partial<ProjectInput> & { is_archived?: boolean }
): Promise<Project> {
  return apiFetch<Project>(`/api/v1/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function deleteProject(id: number): Promise<void> {
  return apiFetch<void>(`/api/v1/projects/${id}`, { method: "DELETE" });
}
