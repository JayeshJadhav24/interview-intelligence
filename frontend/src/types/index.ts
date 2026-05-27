export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type SessionStatus = "pending" | "in_progress" | "completed";

export interface Session {
  id: string;
  job_role: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: string;
  name: string;
  category: string;
  confidence_score: number;
  years_experience: number | null;
  is_bluff_risk: boolean;
}

export type QuestionType =
  | "conceptual"
  | "practical"
  | "behavioral"
  | "bluff_check"
  | "follow_up";

export type DifficultyLevel = "easy" | "medium" | "hard";

export interface Question {
  id: string;
  text: string;
  question_type: QuestionType;
  difficulty: DifficultyLevel;
  order_index: number;
  skill_id: string | null;
}

export interface Answer {
  id: string;
  question_id: string;
  text: string;
  quality_score: number | null;
  is_bluff_detected: boolean;
  follow_up_generated: boolean;
}

export interface SubmitAnswerResult {
  answer: Answer;
  quality_score: number;
  is_bluff_detected: boolean;
  reasoning: string;
  follow_up_question: Question | null;
}

export interface Evaluation {
  id: string;
  session_id: string;
  overall_score: number;
  technical_score: number;
  communication_score: number;
  recommendation: string;
  strengths: string;
  gaps: string;
  bluff_summary: string;
  full_report: string;
  created_at: string;
}
