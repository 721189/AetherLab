"use client";

import { Bot, User } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/utils";
import type { Message } from "@/types";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <span
        className={cn(
          "mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </span>
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm",
          isUser
            ? "rounded-tr-sm bg-primary text-primary-foreground"
            : "rounded-tl-sm bg-muted"
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        <p
          className={cn(
            "mt-1 text-right text-[10px]",
            isUser ? "text-primary-foreground/70" : "text-muted-foreground"
          )}
        >
          {formatTime(message.created_at)}
        </p>
      </div>
    </motion.div>
  );
}