import { RedirectIfAuthed } from "@/components/auth/guards";

export const metadata = {
  title: "Auth — AetherLab",
};

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RedirectIfAuthed>
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-950 via-emerald-950/40 to-slate-950 p-4">
        {children}
      </div>
    </RedirectIfAuthed>
  );
}
