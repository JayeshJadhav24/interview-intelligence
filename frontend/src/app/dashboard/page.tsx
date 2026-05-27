"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { sessionsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { Session } from "@/types";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  in_progress: "In Progress",
  completed: "Completed",
};

const STATUS_VARIANTS: Record<
  string,
  "default" | "secondary" | "outline" | "destructive"
> = {
  pending: "secondary",
  in_progress: "default",
  completed: "outline",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function DashboardPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const { clearAuth } = useAuthStore();
  const router = useRouter();

  const loadSessions = useCallback(async () => {
    try {
      const res = await sessionsApi.list();
      setSessions(
        [...res.data].sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        )
      );
    } catch {
      clearAuth();
      router.replace("/auth");
    } finally {
      setLoading(false);
    }
  }, [clearAuth, router]);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/auth");
      return;
    }
    loadSessions();
  }, [loadSessions, router]);

  const handleDelete = async (id: string) => {
    try {
      await sessionsApi.delete(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
    } catch {
      // ignore
    }
  };

  const handleLogout = () => {
    clearAuth();
    router.replace("/auth");
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Navbar */}
      <header className="border-b border-border bg-card px-4">
        <div className="max-w-5xl mx-auto h-14 flex items-center justify-between">
          <span className="font-semibold text-base">Interview Intelligence</span>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Interview Sessions</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {sessions.length} session{sessions.length !== 1 ? "s" : ""}
            </p>
          </div>
          <Link href="/sessions/new">
            <Button>New Interview</Button>
          </Link>
        </div>

        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-20 mt-1" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-3 w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-16 space-y-3">
            <p className="text-muted-foreground">
              No interview sessions yet
            </p>
            <Link href="/sessions/new">
              <Button>Start your first interview</Button>
            </Link>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {sessions.map((session) => (
              <Card key={session.id}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">{session.job_role}</CardTitle>
                    <Badge variant={STATUS_VARIANTS[session.status] ?? "secondary"}>
                      {STATUS_LABELS[session.status] ?? session.status}
                    </Badge>
                  </div>
                  <CardDescription>{formatDate(session.created_at)}</CardDescription>
                </CardHeader>
                <CardFooter className="gap-2">
                  {session.status === "completed" ? (
                    <Link href={`/sessions/${session.id}/report`}>
                      <Button size="sm">View Report</Button>
                    </Link>
                  ) : (
                    <Link href={`/sessions/${session.id}/interview`}>
                      <Button size="sm">
                        {session.status === "pending"
                          ? "Start Interview"
                          : "Continue"}
                      </Button>
                    </Link>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDelete(session.id)}
                  >
                    Delete
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
