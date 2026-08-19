"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Cloud,
  FolderKanban,
  Thermometer,
  Plus,
} from "lucide-react";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectCard } from "@/components/projects/ProjectCard";
import { ProjectFormDialog } from "@/components/projects/ProjectFormDialog";
import { useProjects } from "@/hooks/useProjects";
import { useLatestEnv } from "@/hooks/useEnvironmental";
import { aqiColor, aqiLabel } from "@/lib/utils";

const DEFAULT_CITY = "London";

export default function DashboardPage() {
  const { data: projects, isLoading } = useProjects();
  const { data: latest, isLoading: envLoading } = useLatestEnv(DEFAULT_CITY, 1);
  const [dialogOpen, setDialogOpen] = useState(false);

  const reading = latest?.[0];

  const stats = [
    {
      label: "Air Quality Index",
      value: reading && reading.aqi != null ? String(reading.aqi) : "—",
      sub: reading && reading.aqi != null ? aqiLabel(reading.aqi) : "Awaiting data",
      icon: Activity,
      accent: reading?.aqi != null ? aqiColor(reading.aqi) : "#64748b",
    },
    {
      label: "Temperature",
      value: reading && reading.temperature != null ? `${Math.round(reading.temperature)}°` : "—",
      sub: DEFAULT_CITY,
      icon: Thermometer,
      accent: "#22c55e",
    },
    {
      label: "Active Projects",
      value: String(projects?.filter((p) => !p.is_archived).length ?? 0),
      sub: "across your workspace",
      icon: FolderKanban,
      accent: "#06b6d4",
    },
  ];

  const recent = (projects ?? []).slice(0, 3);

  return (
    <div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Welcome back. Here’s what is happening.
        </p>
      </motion.div>

      <div className="grid gap-4 sm:grid-cols-3">
        {stats.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {s.label}
                </CardTitle>
                <span style={{ color: s.accent }}>
                  <s.icon className="h-5 w-5" />
                </span>
              </CardHeader>
              <CardContent>
                {envLoading && (s.label === "Air Quality Index" || s.label === "Temperature") ? (
                  <Skeleton className="h-8 w-20" />
                ) : (
                  <div className="text-3xl font-bold">{s.value}</div>
                )}
                <p className="mt-1 text-xs text-muted-foreground">{s.sub}</p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Recent projects</h2>
            <Link href="/projects" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
              View all <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Skeleton className="h-40" />
              <Skeleton className="h-40" />
            </div>
          ) : recent.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {recent.map((project, i) => (
                <ProjectCard key={project.id} project={project} index={i} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
              <Cloud className="h-8 w-8" />
              <p>No projects yet.</p>
              <Button size="sm" onClick={() => setDialogOpen(true)}>
                <Plus className="h-4 w-4" /> Create your first project
              </Button>
            </div>
          )}
        </div>
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Quick actions</h2>
          <div className="space-y-3">
            <Button asChild variant="outline" className="w-full justify-between">
              <Link href="/projects">
                Manage projects <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-between">
              <Link href="/agents">
                Configure agents <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full justify-between">
              <Link href="/environmental">
                Environmental monitor <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </div>

      <ProjectFormDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}