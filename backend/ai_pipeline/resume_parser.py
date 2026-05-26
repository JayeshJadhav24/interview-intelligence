import io

import fitz  # PyMuPDF

from ai_pipeline.llm_client import structured_completion
from ai_pipeline.schemas import ResumeParseResult

_SYSTEM = """You are an expert technical recruiter and resume analyst.
Extract a structured skill graph from the resume text provided.
Return valid JSON matching the schema exactly.
Be conservative with confidence scores — only give 0.9+ if the skill is explicitly
mentioned with clear evidence. Flag is_bluff_risk=true if a skill is claimed at a
senior level but the evidence is thin or contradictory."""

_PROMPT_TEMPLATE = """Analyze this resume and extract all technical and soft skills.

Resume text:
---
{resume_text}
---

Return JSON with this exact structure:
{{
  "candidate_name": "string or null",
  "total_experience_years": number or null,
  "skills": [
    {{
      "name": "skill name",
      "category": "backend|frontend|database|devops|cloud|mobile|soft_skill|other",
      "confidence_score": 0.0-1.0,
      "years_experience": number or null,
      "is_bluff_risk": boolean,
      "evidence": "direct quote or context from resume"
    }}
  ],
  "bluff_risk_flags": ["list of skill names flagged as risky"],
  "summary": "2-3 sentence professional summary"
}}"""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages).strip()


async def parse_resume(pdf_bytes: bytes) -> ResumeParseResult:
    resume_text = extract_text_from_pdf(pdf_bytes)
    prompt = _PROMPT_TEMPLATE.format(resume_text=resume_text[:12000])  # cap at ~12k chars
    return await structured_completion(
        prompt=prompt,
        system=_SYSTEM,
        response_schema=ResumeParseResult,
    )


async def parse_resume_from_text(resume_text: str) -> ResumeParseResult:
    prompt = _PROMPT_TEMPLATE.format(resume_text=resume_text[:12000])
    return await structured_completion(
        prompt=prompt,
        system=_SYSTEM,
        response_schema=ResumeParseResult,
    )
