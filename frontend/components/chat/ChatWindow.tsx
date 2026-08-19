"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { Composer } from "@/components/chat/Composer";
import * as convApi from "@/lib/api/conversations";
import type { Message } from "@/types";

interface ChatWindowProps {
  projectId: number;
  conversationId: number;
}

export function ChatWindow({ projectId, conversationId }: ChatWindowProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Reset local history when switching conversations (the backend exposes no
  // history endpoint, so history accumulates during the session).
  useEffect(() => {
    setMessages([]);
  }, [conversationId]);

  const sendMutation = useMutation({
    mutationFn: (content: string) =>
      convApi.sendMessage(projectId, conversationId, content),
    onMutate: (content) => {
      const optimistic: Message = {
        id: -Date.now(),
        conversation_id: conversationId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev.filter((m) => !(m.id < 0 && m.content === data.user_message.content)),
        data.user_message,
        data.assistant_message,
      ]);
    },
    onError: () => {
      toast.error("Failed to get a reply from the assistant.");
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = (content: string) => {
    sendMutation.mutate(content);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && !sendMutation.isPending ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
            <div className="max-w-sm space-y-2">
              <p className="text-lg font-medium text-foreground">
                Start a conversation
              </p>
              <p>
                Ask about air quality, weather, environmental trends — powered by
                a free Nemotron model.
              </p>
            </div>
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}
        {sendMutation.isPending && messages.length === 0 && null}
        <div ref={scrollRef} />
      </div>
      <Composer
        onSend={handleSend}
        busy={sendMutation.isPending}
        disabled={!conversationId}
      />
    </div>
  );
}