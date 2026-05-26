from ai_pipeline.llm_client import structured_completion
from ai_pipeline.schemas import JDAnalysisResult

_SYSTEM = """You are an expert technical recruiter.
Analyze the job description and extract structured role requirements.
Return valid JSON matching the schema exactly."""

_PROMPT_TEMPLATE = """Analyze this job description and extract all role requirements.

Job Description:
---
{jd_text}
---

Return JSON with this exact structure:
{{
  "job_title": "string",
  "seniority_level": "junior|mid|senior|lead|principal",
  "required_skills": [
    {{
      "skill": "skill name",
      "category": "backend|frontend|database|devops|cloud|mobile|soft_skill|other",
      "importance": "required|preferred|nice_to_have",
      "min_years": number or null
    }}
  ],
  "key_responsibilities": ["list of main responsibilities"],
  "summary": "2-3 sentence summary of the role"
}}"""


async def analyze_jd(jd_text: str) -> JDAnalysisResult:
    prompt = _PROMPT_TEMPLATE.format(jd_text=jd_text[:8000])
    return await structured_completion(
        prompt=prompt,
        system=_SYSTEM,
        response_schema=JDAnalysisResult,
    )
