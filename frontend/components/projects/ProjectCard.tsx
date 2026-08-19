"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { FolderKanban, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { timeAgo } from "@/lib/utils";
import type { Project } from "@/types";

export function ProjectCard({ project, index = 0 }: { project: Project; index?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Link href={`/projects/${project.id}`}>
        <Card className="group h-full transition-shadow hover:shadow-md">
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FolderKanban className="h-5 w-5" />
              </span>
              <CardTitle className="text-base group-hover:text-primary">
                {project.name}
              </CardTitle>
            </div>
            {project.is_archived && <Badge variant="secondary">Archived</Badge>}
          </CardHeader>
          <CardContent>
            <p className="line-clamp-2 text-sm text-muted-foreground">
              {project.description || "No description provided."}
            </p>
            <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
              <span>Updated {timeAgo(project.updated_at)}</span>
              <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </div>
          </CardContent>
        </Card>
      </Link>
    </motion.div>
  );
}
