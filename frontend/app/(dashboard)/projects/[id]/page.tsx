"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AgentCard } from "@/components/agents/AgentCard";
import { AgentFormDialog } from "@/components/agents/AgentFormDialog";
import { ConversationList } from "@/components/chat/ConversationList";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ProjectFormDialog } from "@/components/projects/ProjectFormDialog";
import {
  useProject,
  useDeleteProject,
  useUpdateProject,
} from "@/hooks/useProjects";
import { useAgents, useArchiveAgent } from "@/hooks/useAgents";
import type { Agent } from "@/types";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = Number(params.id);
  const router = useRouter();

  const { data: project, isLoading } = useProject(projectId);
  const { data: agents } = useAgents(projectId);
  const deleteProject = useDeleteProject();
  const archiveAgent = useArchiveAgent(projectId);
  const updateProject = useUpdateProject();

  const [agentDialogOpen, setAgentDialogOpen] = useState(false);
  const [editAgent, setEditAgent] = useState<Agent | undefined>(undefined);
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [activeConv, setActiveConv] = useState<number | null>(null);

  const handleDelete = async () => {
    if (!confirm("Delete this project and all of its data?")) return;
    try {
      await deleteProject.mutateAsync(projectId);
      toast.success("Project deleted");
      router.push("/projects");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleArchive = async () => {
    if (!project) return;
    try {
      await updateProject.mutateAsync({
        id: projectId,
        input: { is_archived: !project.is_archived },
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="space-y-4">
        <p className="text-muted-foreground">Project not found.</p>
        <Button asChild variant="outline">
          <Link href="/projects">Back to projects</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Button asChild variant="ghost" size="sm" className="mb-2">
            <Link href="/projects">
              <ArrowLeft className="h-4 w-4" /> All projects
            </Link>
          </Button>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
            {project.is_archived && <Badge variant="secondary">Archived</Badge>}
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            {project.description || "No description provided."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleArchive}>
            {project.is_archived ? "Restore" : "Archive"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setProjectDialogOpen(true)}>
            Edit
          </Button>
          <Button variant="destructive" size="sm" onClick={handleDelete}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="chat">Conversations</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Agents</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{agents?.length ?? 0}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">
                  {project.is_archived ? "Archived" : "Active"}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Created</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-muted-foreground">
                  {new Date(project.created_at).toLocaleDateString()}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="agents">
          <div className="mb-4 flex justify-end">
            <Button
              onClick={() => {
                setEditAgent(undefined);
                setAgentDialogOpen(true);
              }}
              disabled={project.is_archived}
            >
              <Plus className="h-4 w-4" /> New agent
            </Button>
          </div>
          {agents && agents.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {agents.map((agent, i) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  index={i}
                  onEdit={(a) => {
                    setEditAgent(a);
                    setAgentDialogOpen(true);
                  }}
                  onArchive={(a) => archiveAgent.mutate(a.id)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
              No agents in this project yet.
            </div>
          )}
        </TabsContent>

        <TabsContent value="chat">
          <div className="flex h-[65vh] overflow-hidden rounded-lg border">
            <ConversationList
              projectId={projectId}
              activeId={activeConv}
              onSelect={setActiveConv}
              onCreated={(id) => setActiveConv(id)}
            />
            <div className="flex-1">
              {activeConv ? (
                <ChatWindow projectId={projectId} conversationId={activeConv} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  Select or create a conversation to start chatting.
                </div>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>

      <AgentFormDialog
        projectId={projectId}
        open={agentDialogOpen}
        onOpenChange={setAgentDialogOpen}
        agent={editAgent}
      />
      <ProjectFormDialog
        open={projectDialogOpen}
        onOpenChange={setProjectDialogOpen}
        project={project}
      />
    </div>
  );
}