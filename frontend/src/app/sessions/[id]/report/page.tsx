"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getApiErrorMessage, sessionsApi } from "@/lib/api";
import type { Evaluation } from "@/types";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isFallbackReport = (report: Evaluation | null) =>
    Boolean(
      report?.full_report
        ?.toLowerCase()
        .includes("fallback evaluation report generated in development mode")
    );

  const load = useCallback(async () => {
    try {
      const existing = await sessionsApi.getEvaluation(id);

      // If session has an old fallback report, attempt regeneration with AI.
      if (isFallbackReport(existing.data)) {
        try {
          const regenerated = await sessionsApi.evaluate(id);
          setEvaluation(regenerated.data);
        } catch (regenErr) {
          setEvaluation(existing.data);
          setError(
            getApiErrorMessage(
              regenErr,
              "AI regeneration failed. Showing the previous fallback report."
            )
          );
        }
      } else {
        setEvaluation(existing.data);
      }
    } catch (getErr) {
      try {
        const generated = await sessionsApi.evaluate(id);
        setEvaluation(generated.data);
      } catch (evalErr) {
        const detail = getApiErrorMessage(evalErr, "No evaluation report found for this session.");
        // Prefer more actionable evaluation error over getEvaluation error.
        setError(detail || getApiErrorMessage(getErr, "No evaluation report found for this session."));
      }
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/auth");
      return;
    }
    load();
  }, [load, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm text-muted-foreground">
          Loading evaluation report…
        </p>
      </div>
    );
  }

  if (error || !evaluation) {
    return (
      <div className="min-h-screen flex items-center justify-center flex-col gap-3">
        <p className="text-sm text-destructive">
          {error ?? "Report not available."}
        </p>
        <Button onClick={() => router.push("/dashboard")}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  const isHire =
    evaluation.recommendation?.toLowerCase().includes("hire") &&
    !evaluation.recommendation?.toLowerCase().includes("no hire") &&
    !evaluation.recommendation?.toLowerCase().includes("not hire");

  const techPct = Math.min(Math.round(evaluation.technical_score * 10), 100);
  const commPct = Math.min(
    Math.round(evaluation.communication_score * 10),
    100
  );
  const overallPct = Math.min(Math.round(evaluation.overall_score * 10), 100);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card px-4">
        <div className="max-w-3xl mx-auto h-14 flex items-center justify-between">
          <span className="font-semibold text-base">Evaluation Report</span>
          <Link href="/dashboard">
            <Button variant="outline" size="sm">
              Dashboard
            </Button>
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {error && (
          <div className="rounded-lg bg-destructive/10 text-destructive px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {/* Overall score + recommendation */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs text-muted-foreground mb-1">
                  Overall Score
                </p>
                <p className="text-4xl font-bold">
                  {evaluation.overall_score.toFixed(1)}
                  <span className="text-lg font-normal text-muted-foreground">
                    /10
                  </span>
                </p>
              </div>
              <div
                className={`px-4 py-2 rounded-xl text-sm font-semibold ${
                  isHire
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {evaluation.recommendation}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Score breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Score Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <div className="flex justify-between text-sm">
                <span>Technical</span>
                <span className="font-medium">
                  {evaluation.technical_score.toFixed(1)}/10
                </span>
              </div>
              <Progress value={techPct} />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-sm">
                <span>Communication</span>
                <span className="font-medium">
                  {evaluation.communication_score.toFixed(1)}/10
                </span>
              </div>
              <Progress value={commPct} />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-sm">
                <span>Overall</span>
                <span className="font-medium">
                  {evaluation.overall_score.toFixed(1)}/10
                </span>
              </div>
              <Progress value={overallPct} />
            </div>
          </CardContent>
        </Card>

        {/* Strengths */}
        <Card>
          <CardHeader>
            <CardTitle className="text-emerald-700">Strengths</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-line leading-relaxed">
              {evaluation.strengths}
            </p>
          </CardContent>
        </Card>

        {/* Gaps */}
        <Card>
          <CardHeader>
            <CardTitle className="text-orange-700">
              Areas for Improvement
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-line leading-relaxed">
              {evaluation.gaps}
            </p>
          </CardContent>
        </Card>

        {/* Bluff summary */}
        {evaluation.bluff_summary && (
          <Card>
            <CardHeader>
              <CardTitle>Bluff Detection Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm whitespace-pre-line leading-relaxed">
                {evaluation.bluff_summary}
              </p>
            </CardContent>
          </Card>
        )}

        <Separator />

        {/* Full report */}
        <Card>
          <CardHeader>
            <CardTitle>Full Report</CardTitle>
            <CardDescription>
              Detailed assessment from the AI interviewer
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-line leading-relaxed">
              {evaluation.full_report}
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
