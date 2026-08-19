"use client";

import { MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useConversations, useCreateConversation } from "@/hooks/useConversations";

interface ConversationListProps {
  projectId: number;
  activeId?: number | null;
  onSelect: (id: number) => void;
  onCreated: (id: number) => void;
}

export function ConversationList({
  projectId,
  activeId,
  onSelect,
  onCreated,
}: ConversationListProps) {
  const { data: conversations, isLoading } = useConversations(projectId);
  const createConversation = useCreateConversation(projectId);

  const handleNew = async () => {
    try {
      const conv = await createConversation.mutateAsync({ title: "New conversation" });
      onCreated(conv.id);
    } catch {
      /* toast handled elsewhere */
    }
  };

  return (
    <div className="flex h-full w-64 flex-col border-r">
      <div className="border-b p-3">
        <Button
          variant="secondary"
          className="w-full"
          onClick={handleNew}
          disabled={createConversation.isPending}
        >
          <MessageSquarePlus className="h-4 w-4" />
          New chat
        </Button>
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {isLoading ? (
          <p className="px-2 py-4 text-xs text-muted-foreground">Loading…</p>
        ) : conversations && conversations.length > 0 ? (
          conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => onSelect(conv.id)}
              className={cn(
                "w-full truncate rounded-md px-3 py-2 text-left text-sm transition-colors",
                activeId === conv.id
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent"
              )}
            >
              {conv.title || `Conversation ${conv.id}`}
            </button>
          ))
        ) : (
          <p className="px-2 py-4 text-xs text-muted-foreground">
            No conversations yet.
          </p>
        )}
      </div>
    </div>
  );
}