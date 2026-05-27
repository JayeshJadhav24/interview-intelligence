"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { sessionsApi } from "@/lib/api";

const schema = z.object({
  job_role: z.string().min(1, "Job role is required"),
  jd_text: z.string().optional(),
  resume_text: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

type ApiError = { response?: { data?: { detail?: string } } };

export default function NewSessionPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeFile, setResumeFile] = useState<File | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormValues) => {
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("job_role", data.job_role);
      if (data.jd_text) formData.append("jd_text", data.jd_text);
      if (data.resume_text) formData.append("resume_text", data.resume_text);
      if (resumeFile) formData.append("resume_file", resumeFile);

      const res = await sessionsApi.create(formData);
      router.push(`/sessions/${res.data.id}/interview`);
    } catch (err: unknown) {
      const msg = (err as ApiError)?.response?.data?.detail;
      setError(msg ?? "Failed to create session. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card px-4">
        <div className="max-w-3xl mx-auto h-14 flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Back
          </button>
          <span className="font-semibold text-base">New Interview Session</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {error && (
            <div className="rounded-lg bg-destructive/10 text-destructive px-3 py-2 text-sm">
              {error}
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Job Details</CardTitle>
              <CardDescription>
                Tell us about the role you&apos;re interviewing for
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="job_role">Job Role *</Label>
                <Input
                  id="job_role"
                  placeholder="e.g. Senior Software Engineer"
                  {...register("job_role")}
                />
                {errors.job_role && (
                  <p className="text-xs text-destructive">
                    {errors.job_role.message}
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="jd_text">Job Description (optional)</Label>
                <Textarea
                  id="jd_text"
                  placeholder="Paste the job description here…"
                  style={{ minHeight: "120px" }}
                  {...register("jd_text")}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Resume</CardTitle>
              <CardDescription>
                Upload a file or paste your resume text
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="resume_file">Upload Resume</Label>
                <input
                  id="resume_file"
                  type="file"
                  accept=".pdf,.txt,.doc,.docx"
                  className="w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer"
                  onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
                />
                {resumeFile && (
                  <p className="text-xs text-muted-foreground">
                    {resumeFile.name}
                  </p>
                )}
              </div>

              <div className="relative flex items-center gap-3">
                <div className="flex-1 border-t border-border" />
                <span className="text-xs text-muted-foreground">
                  or paste text
                </span>
                <div className="flex-1 border-t border-border" />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="resume_text">Resume Text</Label>
                <Textarea
                  id="resume_text"
                  placeholder="Paste your resume content here…"
                  style={{ minHeight: "150px" }}
                  {...register("resume_text")}
                />
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.back()}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Creating session…" : "Start Interview"}
            </Button>
          </div>
        </form>
      </main>
    </div>
  );
}
