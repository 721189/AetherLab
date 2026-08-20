"use client";

import { Component, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    console.error("[ErrorBoundary] Render error:", error);
    console.error(info?.componentStack ?? "no component stack");
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? <ErrorFallback onReset={this.reset} />;
    }
    return this.props.children;
  }
}

function ErrorFallback({ onReset }: { onReset: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-destructive bg-destructive/5 p-8 text-center">
      <h3 className="text-lg font-semibold">Something went wrong</h3>
      <p className="text-sm text-muted-foreground">
        An unexpected error occurred while rendering this section.
      </p>
      <Button size="sm" variant="outline" onClick={onReset}>
        Retry
      </Button>
    </div>
  );
}

/**
 * Wraps children in an {@link ErrorBoundary} whose retry action invalidates the
 * React Query cache and reloads the page — a true "retry" for route-level
 * errors thrown during data fetching or rendering.
 */
export function RetryOnError({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const handleReset = () => {
    // Drop cached data so queries refetch on the reload that follows.
    void queryClient.resetQueries();
    window.location.reload();
  };

  return (
    <ErrorBoundary fallback={<ErrorFallback onReset={handleReset} />}>
      {children}
    </ErrorBoundary>
  );
}
