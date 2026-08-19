"use client";

import { motion } from "framer-motion";
import { Bot, Pencil, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StatusBadge } from "@/components/agents/StatusBadge";
import type { Agent } from "@/types";

interface AgentCardProps {
  agent: Agent;
  onEdit: (agent: Agent) => void;
  onArchive: (agent: Agent) => void;
  index?: number;
}

export function AgentCard({ agent, onEdit, onArchive, index = 0 }: AgentCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card className="h-full">
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
          <p className="line-clamp-3 text-sm text-muted-foreground">
            {agent.description || "No description."}
          </p>
          <div className="flex items-center justify-between border-t pt-3">
            <span className="text-xs text-muted-foreground">
              temp {agent.temperature}
              {agent.max_tokens ? ` · max ${agent.max_tokens}` : ""}
              {agent.is_public ? " · public" : ""}
            </span>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onEdit(agent)}
              >
                <Pencil className="h-4 w-4" />
                Edit
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onArchive(agent)}
              >
                <Archive className="h-4 w-4" />
                Archive
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}