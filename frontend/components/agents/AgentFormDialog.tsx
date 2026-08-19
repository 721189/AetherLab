"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { agentSchema, type AgentValues } from "@/lib/validations";
import { useCreateAgent, useUpdateAgent } from "@/hooks/useAgents";
import { AGENT_STATUSES, type Agent } from "@/types";

interface AgentFormDialogProps {
  projectId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent?: Agent;
}

export function AgentFormDialog({
  projectId,
  open,
  onOpenChange,
  agent,
}: AgentFormDialogProps) {
  const createAgent = useCreateAgent(projectId);
  const updateAgent = useUpdateAgent(projectId);
  const editing = Boolean(agent);

  const form = useForm<AgentValues>({
    resolver: zodResolver(agentSchema),
    defaultValues: {
      name: agent?.name ?? "",
      description: agent?.description ?? "",
      model: agent?.model ?? "nvidia/nemotron-4-340b-base",
      system_prompt: agent?.system_prompt ?? "",
      temperature: agent?.temperature ?? 0.7,
      max_tokens: agent?.max_tokens ?? 2048,
      status: agent?.status ?? "inactive",
      is_public: agent?.is_public ?? false,
    },
  });

  const onSubmit = async (values: AgentValues) => {
    const input = {
      name: values.name,
      description: values.description || null,
      model: values.model,
      system_prompt: values.system_prompt || null,
      temperature: Number(values.temperature),
      max_tokens: values.max_tokens ? Number(values.max_tokens) : null,
      status: values.status,
      is_public: values.is_public ?? false,
    };
    try {
      if (agent) {
        await updateAgent.mutateAsync({ agentId: agent.id, input });
        toast.success("Agent updated");
      } else {
        await createAgent.mutateAsync(input);
        toast.success("Agent created");
      }
      onOpenChange(false);
      form.reset();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save agent");
    }
  };

  const busy = createAgent.isPending || updateAgent.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit agent" : "New agent"}</DialogTitle>
          <DialogDescription>
            Configure an AI agent powered by a free Nemotron model via OpenRouter.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Air Monitor" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Status</FormLabel>
                    <FormControl>
                      <Select value={field.value} onChange={field.onChange}>
                        {AGENT_STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="model"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Model</FormLabel>
                  <FormControl>
                    <Input placeholder="nvidia/nemotron-4-340b-base" {...field} />
                  </FormControl>
                  <FormDescription>
                    Free Nemotron models via OpenRouter (e.g. nvidia/nemotron-4-340b-base).
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
<FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea placeholder="What does this agent do?" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="system_prompt"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>System prompt</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="You are a helpful environmental analyst..."
                      className="min-h-[80px]"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="temperature"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Temperature{" "}
                      <span className="text-muted-foreground">({field.value})</span>
                    </FormLabel>
                    <FormControl>
                      <Slider
                        min={0}
                        max={2}
                        step={0.1}
                        value={[Number(field.value) || 0]}
                        onValueChange={(v) => field.onChange(v[0])}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="max_tokens"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max tokens</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={4096}
                        {...field}
                        value={field.value ?? ""}
                        onChange={(e) =>
                          field.onChange(e.target.value ? Number(e.target.value) : null)
                        }
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="is_public"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2 space-y-0">
                  <FormControl>
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={Boolean(field.value)}
                      onChange={(e) => field.onChange(e.target.checked)}
                    />
                  </FormControl>
                  <FormLabel className="cursor-pointer">Public agent</FormLabel>
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                {editing ? "Save changes" : "Create agent"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}