"use client";

import { useRouter } from "next/navigation";
import { LogOut, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/store/authStore";

export function TopBar() {
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      <div />
      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-2 text-sm text-muted-foreground sm:flex">
          <User className="h-4 w-4" />
          {user?.email ?? "Account"}
        </div>
        <Button variant="outline" size="sm" onClick={handleLogout}>
          <LogOut className="h-4 w-4" />
          Log out
        </Button>
      </div>
    </header>
  );
}