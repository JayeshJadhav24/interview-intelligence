---
mode: agent
description: >
  Writes all Next.js 14 App Router frontend code: pages, components, hooks,
  Zustand stores, typed API client, Supabase Auth integration, and TypeScript types.
  Server components by default, 'use client' only when required. Shows every file
  before creating it and suggests commits after each page is complete.
tools:
  - codebase
  - editFiles
  - runCommand
  - terminalLastCommand
---

# Frontend Agent

You write clean, fully-typed Next.js 14 code. No `any`. Server components by default.
Show every file before creating it. Ask which page to build first.

---

## Opening Questions

```
1. "Which page or component are we building?
   A) Shared types + API client + Supabase setup
   B) Auth pages (login / signup)
   C) Session list + new session upload
   D) Skill graph page
   E) Interview dashboard (question list)
   F) Live interview flow
   G) Evaluation report"

2. "Server or client component?
   I'll recommend but you confirm."

3. "Show file before creating? (yes — always)"
```

---

## Component Decision Rule

```
Server Component (default, NO "use client"):
  ✅ Pages that fetch data (use async/await in component)
  ✅ Layouts
  ✅ Static display content

Client Component ("use client" required):
  ✅ useState, useEffect, event handlers
  ✅ Forms (react-hook-form)
  ✅ Real-time updates (follow-up reveal, progress)
  ✅ Zustand store consumers
```

---

## `types/index.ts`

```typescript
export type SessionStatus = "created"|"parsing"|"ready"|"in_progress"|"completed";
export type SkillLevel = "beginner"|"intermediate"|"advanced";
export type QuestionDifficulty = "easy"|"medium"|"hard"|"verification";
export type AnswerQuality = "weak"|"adequate"|"strong";
export type Recommendation = "hire"|"borderline"|"no_hire";

export interface Session {
  id: string;
  candidate_name: string;
  job_title: string;
  status: SessionStatus;
  created_at: string;
  completed_at: string | null;
  resume_url?: string;
  jd_text?: string;
}

export interface Skill {
  id: string;
  session_id: string;
  skill_name: string;
  category: string;
  level: SkillLevel;
  confidence: number;
  evidence: string[];
  bluff_risk: boolean;
  bluff_reason: string | null;
}

export interface Question {
  id: string;
  session_id: string;
  skill_id: string;
  question_text: string;
  difficulty: QuestionDifficulty;
  question_type: string;
  order_index: number;
  asked: boolean;
}

export interface Answer {
  id: string;
  question_id: string;
  answer_text: string;
  quality: AnswerQuality;
  follow_up_text: string | null;
  follow_up_used: boolean;
  bluff_verdict: "verified"|"likely_inflated"|"inconclusive"|null;
}

export interface Evaluation {
  id: string;
  overall_score: number;
  recommendation: Recommendation;
  narrative: string;
  skill_scores: Record<string, number>;
  strengths: string[];
  gaps: string[];
  bluff_summary: string | null;
  created_at: string;
}
```

---

## `lib/api.ts`

```typescript
import axios, { AxiosError } from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use(async (config) => {
  if (typeof window !== "undefined") {
    const { createBrowserClient } = await import("@supabase/ssr");
    const supabase = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`;
    }
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    if (error.response?.status === 401) window.location.href = "/login";
    return Promise.reject(error);
  }
);

export default api;
```

---

## `middleware.ts`

```typescript
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet) => {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          );
        },
      },
    }
  );
  const { data: { user } } = await supabase.auth.getUser();
  const isAuth = ["/login", "/signup"].some(p =>
    request.nextUrl.pathname.startsWith(p)
  );
  const isProtected = request.nextUrl.pathname.startsWith("/sessions") ||
    request.nextUrl.pathname === "/dashboard";

  if (!user && isProtected) return NextResponse.redirect(new URL("/login", request.url));
  if (user && isAuth) return NextResponse.redirect(new URL("/sessions", request.url));
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

---

## Zustand Store — `hooks/useInterview.ts`

```typescript
"use client";
import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type { Question, Answer, AnswerQuality } from "@/types";
import api from "@/lib/api";

interface InterviewState {
  questions: Question[];
  currentIndex: number;
  currentAnswer: string;
  answers: Answer[];
  currentFollowUp: string | null;
  isSubmitting: boolean;

  setQuestions: (q: Question[]) => void;
  setCurrentAnswer: (a: string) => void;
  submitAnswer: (sessionId: string, questionId: string, quality: AnswerQuality) => Promise<Answer>;
  nextQuestion: () => void;
  reset: () => void;
}

export const useInterview = create<InterviewState>()(
  devtools((set, get) => ({
    questions: [], currentIndex: 0, currentAnswer: "",
    answers: [], currentFollowUp: null, isSubmitting: false,

    setQuestions: (questions) => set({ questions }),
    setCurrentAnswer: (currentAnswer) => set({ currentAnswer }),

    submitAnswer: async (sessionId, questionId, quality) => {
      set({ isSubmitting: true });
      try {
        const { data } = await api.post<Answer>(`/sessions/${sessionId}/answers`, {
          question_id: questionId,
          answer_text: get().currentAnswer,
          quality,
        });
        set(s => ({
          answers: [...s.answers, data],
          currentFollowUp: data.follow_up_text,
          currentAnswer: "",
        }));
        return data;
      } finally {
        set({ isSubmitting: false });
      }
    },

    nextQuestion: () => set(s => ({ currentIndex: s.currentIndex + 1, currentFollowUp: null })),
    reset: () => set({ questions: [], currentIndex: 0, currentAnswer: "",
                       answers: [], currentFollowUp: null, isSubmitting: false }),
  }), { name: "interview-store" })
);
```

---

## `components/interview/QuestionCard.tsx`

```typescript
"use client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { Question } from "@/types";
import { cn } from "@/lib/utils";

const COLORS: Record<string, string> = {
  easy: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  hard: "bg-orange-100 text-orange-800",
  verification: "bg-red-100 text-red-800",
};

export function QuestionCard({ question, num, total }: {
  question: Question; num: number; total: number;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <span className="text-sm text-muted-foreground">Question {num} of {total}</span>
        <Badge className={cn(COLORS[question.difficulty])}>{question.difficulty}</Badge>
      </CardHeader>
      <CardContent>
        <p className="text-lg font-medium leading-relaxed">{question.question_text}</p>
      </CardContent>
    </Card>
  );
}
```

---

## `components/report/ScoreGauge.tsx`

```typescript
"use client";
import type { Recommendation } from "@/types";
import { cn } from "@/lib/utils";

const CONFIG: Record<Recommendation, { label: string; color: string }> = {
  hire: { label: "Hire", color: "text-green-600" },
  borderline: { label: "Borderline", color: "text-yellow-600" },
  no_hire: { label: "No Hire", color: "text-red-600" },
};

export function ScoreGauge({ score, recommendation }: {
  score: number; recommendation: Recommendation;
}) {
  const { label, color } = CONFIG[recommendation];
  const c = 2 * Math.PI * 54;
  const offset = c - (score / 100) * c;
  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle cx="70" cy="70" r="54" fill="none" stroke="#e5e7eb" strokeWidth="12" />
        <circle cx="70" cy="70" r="54" fill="none" stroke="currentColor"
          strokeWidth="12" strokeDasharray={c} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 70 70)" className={color} />
        <text x="70" y="66" textAnchor="middle" fontSize="28" fontWeight="bold"
          fill="currentColor">{score}</text>
        <text x="70" y="84" textAnchor="middle" fontSize="11" fill="#6b7280">/100</text>
      </svg>
      <span className={cn("text-xl font-semibold", color)}>{label}</span>
    </div>
  );
}
```

---

## Quality Check Before Committing

```bash
cd frontend
npm run lint
npm run build
```

Fix all TypeScript errors before committing. `npm run build` catches more than `tsc` alone.

---

## Commit Suggestions

```
feat(frontend): add shared TypeScript types and typed axios API client
feat(frontend): add auth middleware for route protection
feat(frontend): add login and signup pages with Supabase Auth
feat(frontend): add Zustand interview store with answer submission
feat(frontend): add session list and upload pages with drag-drop resume input
feat(frontend): add skill graph page with confidence bars and bluff risk flags
feat(frontend): add interview dashboard with question grouping by difficulty
feat(frontend): add live interview flow with adaptive follow-up reveal
feat(frontend): add evaluation report page with score gauge and skill scores
```
