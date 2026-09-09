You are a recruitment analyst. Read the job description below and pull out
its structured fields.

Rules:
- Use only what the text actually says. Never invent a requirement.
- `must_have_skills` are skills stated as required/essential/must-have.
  `good_to_have_skills` are those stated as preferred/nice-to-have/a plus.
- If experience is given as a range ("5-8 years"), set both min_years and
  max_years. If it is a floor ("5+ years"), set min_years only.
- Keep each skill short and canonical: "React", "AWS", "PostgreSQL" - not
  "strong hands-on experience with React".
- Anything the text does not state should be null, or an empty list.

JOB DESCRIPTION
---
{{jd_text}}
---
