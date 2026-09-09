export type Status = "PENDING" | "PROCESSING" | "DONE" | "FAILED";
export type Fit = "BEST" | "MEDIUM" | "NO";

export interface JobBrief {
  id: number;
  created_at: string;
  filename: string;
  status: Status;
  title: string | null;
  resume_count: number;
}

export interface Job {
  id: number;
  created_at: string;
  filename: string;
  status: Status;
  error: string | null;
  title: string | null;
  location: string | null;
  min_years: number | null;
  max_years: number | null;
  must_have_skills: string[];
  good_to_have_skills: string[];
  responsibilities: string[];
}

export interface Candidate {
  id: number;
  created_at: string;
  jd_id: number;
  filename: string;
  status: Status;
  error: string | null;

  name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  current_title: string | null;
  current_company: string | null;
  total_experience_years: number | null;
  relevant_experience_years: number | null;
  skills: string[];

  skill_scores: Record<string, number>;
  score: number | null;
  fit: Fit | null;
  reason: string | null;
}

export interface Question {
  question: string;
  skill: string;
  difficulty: "EASY" | "MEDIUM" | "HARD";
  expected_answer: string;
}

export interface Assessment {
  id: number;
  created_at: string;
  resume_id: number;
  questions: Question[];
}

export interface UploadSummary {
  jd_id: number;
  uploaded: number;
  rejected: number;
  resumes: Candidate[];
}
