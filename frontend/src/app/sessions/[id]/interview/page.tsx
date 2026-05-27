"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { getApiErrorMessage, sessionsApi } from "@/lib/api";
import type { Question, Session, SubmitAnswerResult } from "@/types";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";

type Phase = "loading" | "processing" | "interview" | "evaluating" | "error";

const TYPE_STYLES: Record<string, string> = {
  conceptual: "bg-blue-100 text-blue-700",
  practical: "bg-green-100 text-green-700",
  behavioral: "bg-purple-100 text-purple-700",
  bluff_check: "bg-orange-100 text-orange-700",
  follow_up: "bg-gray-100 text-gray-600",
};

const DIFFICULTY_STYLES: Record<string, string> = {
  easy: "bg-emerald-100 text-emerald-700",
  medium: "bg-yellow-100 text-yellow-700",
  hard: "bg-red-100 text-red-700",
};

export default function InterviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [phase, setPhase] = useState<Phase>("loading");
  const [session, setSession] = useState<Session | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answerText, setAnswerText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<SubmitAnswerResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const setup = useCallback(async () => {
    try {
      const sessionRes = await sessionsApi.get(id);
      setSession(sessionRes.data);

      if (sessionRes.data.status === "pending") {
        setPhase("processing");
        await sessionsApi.process(id);
      }

      const questionsRes = await sessionsApi.listQuestions(id);
      const sorted = [...questionsRes.data].sort(
        (a, b) => a.order_index - b.order_index
      );
      setQuestions(sorted);
      setPhase("interview");
    } catch (err) {
      console.error(err);
      setErrorMsg(
        getApiErrorMessage(err, "Failed to load interview. Please try again.")
      );
      setPhase("error");
    }
  }, [id]);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/auth");
      return;
    }
    setup();
  }, [setup, router]);

  const submitAnswer = async () => {
    if (!answerText.trim()) return;
    const question = questions[currentIndex];
    setSubmitting(true);
    setFeedback(null);
    try {
      const res = await sessionsApi.submitAnswer(id, question.id, answerText.trim());
      setFeedback(res.data);
      if (res.data.follow_up_question) {
        setQuestions((prev) => {
          const next = [...prev];
          next.splice(currentIndex + 1, 0, res.data.follow_up_question!);
          return next;
        });
      }
    } catch (err) {
      console.error(err);
      setErrorMsg(
        getApiErrorMessage(err, "Failed to submit answer. Please try again.")
      );
    } finally {
      setSubmitting(false);
    }
  };

  const nextQuestion = () => {
    setAnswerText("");
    setFeedback(null);
    setCurrentIndex((i) => i + 1);
  };

  const generateReport = async () => {
    setPhase("evaluating");
    try {
      await sessionsApi.evaluate(id);
      router.replace(`/sessions/${id}/report`);
    } catch (err) {
      console.error(err);
      setErrorMsg(
        getApiErrorMessage(err, "Failed to generate report. Please try again.")
      );
      setPhase("interview");
    }
  };

  if (phase === "loading" || phase === "processing") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-3 max-w-xs">
          <div className="text-sm font-medium">
            {phase === "loading"
              ? "Loading your interview…"
              : "Setting up your interview…"}
          </div>
          {phase === "processing" && (
            <p className="text-xs text-muted-foreground">
              Analyzing your resume and generating personalized questions
            </p>
          )}
        </div>
      </div>
    );
  }

  if (phase === "evaluating") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-2">
          <div className="text-sm font-medium">
            Generating your evaluation report…
          </div>
          <p className="text-xs text-muted-foreground">
            This may take a moment
          </p>
        </div>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-3">
          <p className="text-sm text-destructive">{errorMsg}</p>
          <Button onClick={() => router.push("/dashboard")}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  const allDone = currentIndex >= questions.length;
  const progress =
    questions.length > 0
      ? Math.round((currentIndex / questions.length) * 100)
      : 0;
  const currentQuestion = questions[currentIndex];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card px-4">
        <div className="max-w-3xl mx-auto h-14 flex items-center justify-between">
          <div>
            <span className="font-semibold text-sm">{session?.job_role}</span>
            <span className="text-xs text-muted-foreground ml-2">
              Interview
            </span>
          </div>
          <span className="text-xs text-muted-foreground tabular-nums">
            {allDone ? questions.length : currentIndex + 1} /{" "}
            {questions.length}
          </span>
        </div>
      </header>

      {/* Progress bar */}
      <div className="max-w-3xl mx-auto px-4 pt-4">
        <Progress value={progress} className="h-1.5" />
      </div>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-4">
        {allDone ? (
          /* All questions done */
          <Card>
            <CardHeader>
              <CardTitle>Interview Complete!</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                You&apos;ve answered all {questions.length} questions. Generate
                your evaluation report to see the AI assessment and hire
                recommendation.
              </p>
              {errorMsg && (
                <p className="text-xs text-destructive">{errorMsg}</p>
              )}
              <Button onClick={generateReport}>
                Generate Evaluation Report
              </Button>
            </CardContent>
          </Card>
        ) : (
          /* Active question */
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <span
                  className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    TYPE_STYLES[currentQuestion?.question_type] ??
                    "bg-gray-100 text-gray-600"
                  }`}
                >
                  {currentQuestion?.question_type?.replace("_", " ")}
                </span>
                <span
                  className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    DIFFICULTY_STYLES[currentQuestion?.difficulty] ??
                    "bg-gray-100 text-gray-600"
                  }`}
                >
                  {currentQuestion?.difficulty}
                </span>
              </div>
              <CardTitle className="text-base leading-relaxed">
                {currentQuestion?.text}
              </CardTitle>
            </CardHeader>

            <CardContent className="space-y-4">
              {!feedback ? (
                /* Answer input */
                <>
                  <Textarea
                    placeholder="Type your answer here…"
                    style={{ minHeight: "130px" }}
                    value={answerText}
                    onChange={(e) => setAnswerText(e.target.value)}
                    disabled={submitting}
                  />
                  <Button
                    onClick={submitAnswer}
                    disabled={submitting || !answerText.trim()}
                  >
                    {submitting ? "Evaluating…" : "Submit Answer"}
                  </Button>
                </>
              ) : (
                /* Feedback */
                <div className="space-y-3">
                  <div className="bg-muted/50 rounded-lg p-3 text-sm">
                    <p className="text-xs font-medium text-muted-foreground mb-1">
                      Your answer
                    </p>
                    <p className="leading-relaxed">{answerText}</p>
                  </div>

                  <div className="border border-border rounded-lg p-3 space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-muted-foreground">
                          Quality Score
                        </span>
                        <span className="text-sm font-semibold">
                          {(feedback.quality_score * 10).toFixed(1)}/10
                        </span>
                      </div>
                      {feedback.is_bluff_detected && (
                        <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-medium">
                          ⚠ Bluff detected
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {feedback.reasoning}
                    </p>
                  </div>

                  {feedback.follow_up_question && (
                    <p className="text-xs text-muted-foreground bg-blue-50 px-3 py-2 rounded-lg">
                      A follow-up question has been added to your interview.
                    </p>
                  )}

                  <Button onClick={nextQuestion}>
                    {currentIndex + 1 < questions.length
                      ? "Next Question →"
                      : "Finish Interview"}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
