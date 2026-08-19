"use client";

import { useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ComposerProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  busy?: boolean;
}

export function Composer({ onSend, disabled, busy }: ComposerProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    onSend(text);
    setValue("");
  };

  return (
    <div className="flex items-end gap-2 border-t bg-background p-4">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Message the assistant… (Enter to send, Shift+Enter for newline)"
        className="max-h-32 min-h-[44px] flex-1 resize-none"
        rows={1}
        disabled={disabled}
      />
      <Button onClick={submit} disabled={disabled || busy || !value.trim()} size="icon">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
      </Button>
    </div>
  );
}