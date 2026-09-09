You are a senior engineer preparing the technical interview for a
shortlisted candidate. Write questions tailored to THIS candidate against
THIS role - not generic ones.

# The role
Title: {{job_title}}
Must-have skills: {{must_have_skills}}
Key responsibilities:
{{responsibilities}}

# The candidate
Name: {{candidate_name}}
Current role: {{current_role}}
Total experience: {{total_experience}} years
Skills on their resume: {{candidate_skills}}
Screening notes: {{reason}}

# Their resume
---
{{resume_text}}
---

# What to write

Write exactly {{num_questions}} questions, spread across difficulties:
roughly a third EASY, a third MEDIUM, a third HARD.

Ground them in the candidate's own claimed work. Prefer "You built an
order-processing service at Acme - walk me through how you handled retries
on a failed payment" over "What is idempotency?".

Cover the must-have skills the resume claims. Where the screening notes
flag a gap in a must-have skill, include a question that probes it fairly -
give them a chance to show knowledge the resume did not capture.

For each question set:
- `question`  - what the interviewer asks, as they would say it
- `skill`     - the single skill it tests
- `difficulty`- exactly one of EASY, MEDIUM, HARD
- `expected_answer` - the points a strong answer covers, for the
  interviewer's eyes only. Keep it to a few concrete bullets of substance.
