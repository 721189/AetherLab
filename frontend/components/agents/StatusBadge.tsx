import { Badge } from "@/components/ui/badge";
import type { AgentStatus } from "@/types";

const statusVariant: Record<AgentStatus, "success" | "secondary" | "warning" | "destructive"> = {
  active: "success",
  inactive: "secondary",
  paused: "warning",
  archived: "destructive",
};

export function StatusBadge({ status }: { status: AgentStatus }) {
  return <Badge variant={statusVariant[status]}>{status}</Badge>;
}