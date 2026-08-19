"use client";

import Link from "next/link";
import { useQueries } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/agents/StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useProjects } from "@/hooks/useProjects";
import { agentKeys } from "@/hooks/useAgents";
import * as agentsApi from "@/lib/api/agents";
import type { Agent, Project } from "@/types";

export default function AgentsPage() {
  const { data: projects, isLoading: projectsLoading } = useProjects();

  const agentQueries = useQueries({
    queries: (projects ?? []).map((p) => ({
      queryKey: agentKeys.list(p.id),
      queryFn: () => agentsApi.listAgents(p.id),
      enabled: !!projects && projects.length > 0,
    })),
  });

  const allAgents: Agent[] = [];
  (projects ?? []).forEach((p, i) => {
    if (agentQueries[i]?.data) allAgents.push(...agentQueries[i].data);
  });

  const projectName = (id: number) =>
    (projects ?? []).find((p: Project) => p.id === id)?.name ?? `Project ${id}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
        <p className="text-sm text-muted-foreground">
          All AI agents across your projects.
        </p>
      </div>

      {projectsLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : allAgents.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {allAgents.map((agent) => (
            <Card key={agent.id} className="h-full">
              <CardHeader className="flex-row items-start justify-between space-y-0">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Bot className="h-5 w-5" />
                  </span>
                  <div>
                    <CardTitle className="text-base">{agent.name}</CardTitle>
                    <CardDescription className="text-xs">{agent.model}</CardDescription>
                  </div>
                </div>
                <StatusBadge status={agent.status} />
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {agent.description || "No description."}
                </p>
                <div className="flex items-center justify-between border-t pt-3">
                  <span className="text-xs text-muted-foreground">
                    in <span className="font-medium text-foreground">{projectName(agent.project_id)}</span>
                  </span>
                  <Button asChild variant="ghost" size="sm">
                    <Link href={`/projects/${agent.project_id}`}>Open</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
          No agents yet. Create one from a project page.
        </div>
      )}
    </div>
  );
}