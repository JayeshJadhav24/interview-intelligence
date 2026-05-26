---
mode: agent
description: >
  Implements all 6 AI pipeline modules: resume parser, JD analyzer, question
  generator, adaptive follow-up engine, bluff detector, and evaluation engine.
  Uses Groq (Llama 3.1 70B) for fast pipeline calls and Gemini 1.5 Flash for
  full-session evaluation. Every LLM call is Pydantic-validated with retry logic.
  Shows prompts and code before writing. Asks which module to implement first.
tools:
  - codebase
  - editFiles
  - runCommand
  - terminalLastCommand
---

# AI Pipeline Agent

You implement the LLM integration modules. Every call is validated, retried on failure,
and never trusts raw AI output. Show code and prompts before writing any file.

---

## Opening Questions

```
1. "Which module are we implementing?
   A) client.py — Groq + Gemini setup with retry logic
   B) models.py — Pydantic output schemas for all modules
   C) resume_parser.py
   D) jd_analyzer.py
   E) question_generator.py
   F) followup_engine.py
   G) bluff_detector.py
   H) evaluation_engine.py"

2. "Should I show you the full prompt template before writing the code? (yes)"
3. "Add latency logging to each call? (yes/no — recommended: yes)"
```

---

## `ai_pipeline/models.py` — Output Schemas

Show before writing, ask "Create this file?":

```python
from pydantic import BaseModel, Field


class SkillItem(BaseModel):
    skill_name: str
    category: str
    level: str = Field(pattern="^(beginner|intermediate|advanced)$")
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]
    bluff_risk: bool
    bluff_reason: str | None = None


class ResumeParserOutput(BaseModel):
    candidate_name: str
    total_experience_years: float
    skills: list[SkillItem]


class JDAnalyzerOutput(BaseModel):
    role_title: str
    seniority: str = Field(pattern="^(junior|mid|senior|lead)$")
    primary_domain: str
    required_skills: list[str]
    preferred_skills: list[str]
    key_responsibilities: list[str]


class QuestionItem(BaseModel):
    question_text: str
    difficulty: str = Field(pattern="^(easy|medium|hard|verification)$")
    question_type: str = Field(pattern="^(conceptual|scenario|deep_dive|bluff_check)$")
    expected_answer_depth: str = Field(pattern="^(brief|moderate|detailed)$")
    follow_up_hint: str


class QuestionGeneratorOutput(BaseModel):
    questions: list[QuestionItem]


class FollowUpOutput(BaseModel):
    follow_up_question: str
    reasoning: str
    escalation_direction: str = Field(pattern="^(harder|lateral|simpler)$")


class BluffDetectorOutput(BaseModel):
    verification_question: str
    what_a_genuine_user_would_say: str
    red_flags_indicating_bluff: list[str]


class EvaluationOutput(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    recommendation: str = Field(pattern="^(hire|borderline|no_hire)$")
    narrative: str
    skill_scores: dict[str, int]
    strengths: list[str]
    gaps: list[str]
    bluff_summary: str | None = None
```

---

## `ai_pipeline/client.py`

```python
import time
import logging
from typing import TypeVar, Type
from pydantic import BaseModel, ValidationError
from groq import AsyncGroq
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import get_settings
from app.exceptions import PipelineError

logger = logging.getLogger(__name__)
settings = get_settings()

groq_client = AsyncGroq(api_key=settings.groq_api_key)
genai.configure(api_key=settings.gemini_api_key)

OutputT = TypeVar("OutputT", bound=BaseModel)


async def call_groq_structured(
    system_prompt: str,
    user_message: str,
    output_schema: Type[OutputT],
    stage: str,
    temperature: float = 0.3,
) -> OutputT:
    """Call Groq and validate against Pydantic schema. Retries once on parse failure."""
    start = time.perf_counter()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        response = await groq_client.chat.completions.create(
            model=settings.groq_model, messages=messages,
            temperature=temperature, response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        raise PipelineError(stage, f"Groq API call failed: {e}") from e

    logger.info("groq_call stage=%s latency_ms=%d", stage,
                int((time.perf_counter() - start) * 1000))

    try:
        return output_schema.model_validate_json(raw)
    except (ValidationError, ValueError) as e:
        logger.warning("groq_parse_error stage=%s retrying error=%s", stage, e)
        correction = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": (
                f"Your response failed schema validation: {e}. "
                "Return ONLY valid JSON. No markdown. No explanation."
            )},
        ]
        retry_resp = await groq_client.chat.completions.create(
            model=settings.groq_model, messages=correction,
            temperature=0.0, response_format={"type": "json_object"},
        )
        retry_raw = retry_resp.choices[0].message.content or ""
        try:
            return output_schema.model_validate_json(retry_raw)
        except (ValidationError, ValueError) as retry_e:
            raise PipelineError(stage,
                f"Validation failed after retry. Raw: {retry_raw[:200]}. Error: {retry_e}"
            ) from retry_e


async def call_gemini_structured(
    system_prompt: str,
    user_message: str,
    output_schema: Type[OutputT],
    stage: str,
) -> OutputT:
    """Call Gemini with JSON output mode for large context evaluation."""
    start = time.perf_counter()
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json", temperature=0.2,
        ),
    )
    try:
        response = await model.generate_content_async(user_message)
        raw = response.text
    except Exception as e:
        raise PipelineError(stage, f"Gemini API call failed: {e}") from e

    logger.info("gemini_call stage=%s latency_ms=%d", stage,
                int((time.perf_counter() - start) * 1000))

    try:
        return output_schema.model_validate_json(raw)
    except (ValidationError, ValueError) as e:
        raise PipelineError(stage, f"Gemini schema validation failed: {e}") from e
```

---

## `ai_pipeline/resume_parser.py`

**System Prompt (show to developer, ask "Does this prompt look right?"):**
```
You are a technical resume parser. Extract a structured skill graph from the resume.

Rules:
- Only include skills EXPLICITLY mentioned. Never infer.
- Find at least one verbatim resume quote as evidence per skill.
- bluff_risk=true if: skill appears only in a skills list with no project using it,
  OR mentioned only once with no specific implementation detail.
- confidence: 0.9+ = multiple project references with specifics,
  0.6-0.8 = one project reference, 0.3-0.5 = project list only,
  0.0-0.2 = skills list only.

Return ONLY valid JSON. No explanation text.
```

**Code:**
```python
from ai_pipeline.client import call_groq_structured
from ai_pipeline.models import ResumeParserOutput

SYSTEM_PROMPT = """[paste prompt above]"""


async def parse_resume(resume_text: str) -> dict:
    result = await call_groq_structured(
        system_prompt=SYSTEM_PROMPT,
        user_message=f"Parse this resume:\n\n{resume_text}",
        output_schema=ResumeParserOutput,
        stage="resume_parser",
        temperature=0.1,
    )
    return result.model_dump()
```

---

## `ai_pipeline/question_generator.py`

**System Prompt:**
```
You are an expert technical interviewer generating questions for a specific candidate.

- easy:        "What is X?" — basic conceptual understanding
- medium:      "How did you use X in [specific project from resume]?" — application
- hard:        "How would you scale/debug/optimize X for [scenario]?" — depth
- verification: bluff_risk=true skills only — ask about specific operational detail
               (error message, CLI command, config option, production gotcha) that
               ONLY real hands-on users know. NOT definitional questions.

Rules:
- ALWAYS reference the candidate's specific project/company from resume evidence.
- NEVER generate generic questions applicable to any candidate.
- Generate 3 questions per skill: easy, medium, hard (or verification if bluff_risk=true).

Return ONLY valid JSON.
```

```python
import json
from ai_pipeline.client import call_groq_structured
from ai_pipeline.models import QuestionGeneratorOutput

SYSTEM_PROMPT = """[paste prompt above]"""


async def generate_questions(
    skill_name: str, level: str, evidence: list[str],
    bluff_risk: bool, candidate_name: str, job_title: str,
) -> dict:
    result = await call_groq_structured(
        system_prompt=SYSTEM_PROMPT,
        user_message=json.dumps({
            "skill": {"skill_name": skill_name, "level": level,
                      "evidence": evidence, "bluff_risk": bluff_risk},
            "candidate_name": candidate_name,
            "job_title": job_title,
        }),
        output_schema=QuestionGeneratorOutput,
        stage="question_generator",
        temperature=0.5,
    )
    return result.model_dump()
```

---

## `ai_pipeline/followup_engine.py`

**System Prompt:**
```
You are an adaptive interviewer generating one follow-up question.

- STRONG answer: escalate — edge cases, failure scenarios, scale, tradeoffs
- ADEQUATE answer: lateral — related concept or detail they glossed over
- WEAK answer: simplify — more concrete version of the same concept

The follow-up MUST reference something specific the candidate said.
One sentence maximum. Return ONLY valid JSON.
```

```python
import json
from ai_pipeline.client import call_groq_structured
from ai_pipeline.models import FollowUpOutput

SYSTEM_PROMPT = """[paste prompt above]"""


async def generate_follow_up(
    original_question: str, candidate_answer: str,
    quality: str, skill_context: str,
) -> dict:
    result = await call_groq_structured(
        system_prompt=SYSTEM_PROMPT,
        user_message=json.dumps({
            "original_question": original_question,
            "candidate_answer": candidate_answer,
            "quality": quality,
            "skill_context": skill_context,
        }),
        output_schema=FollowUpOutput,
        stage="followup_engine",
        temperature=0.4,
    )
    return result.model_dump()
```

---

## `ai_pipeline/bluff_detector.py`

**System Prompt:**
```
Detect whether a candidate has genuine hands-on experience with a technology.

Generate ONE verification question answerable ONLY with real production experience:
- Specific error messages or failure modes they'd have encountered
- CLI commands or config file content they'd have typed
- A non-obvious decision with production consequences
- A gotcha or footgun specific to the technology version

Do NOT ask: definitional questions, questions in official docs intro, general concepts.
Return ONLY valid JSON.
```

---

## `ai_pipeline/evaluation_engine.py` — uses Gemini

**System Prompt:**
```
Review a complete interview transcript and evaluate the candidate.

Scoring per skill (0–100):
0–40: No real understanding  |  41–60: Concepts, limited practical depth
61–80: Solid, discusses tradeoffs  |  81–100: Expert, edge cases, scale, failures

Bluff: bluff_risk=true skill + vague/incorrect verification answers = "likely_inflated"
Hire: score≥75, no critical gaps, no bluffs  |  Borderline: 55–74  |  No hire: <55

narrative: 3–4 direct sentences. Name the strongest skill and biggest concern.
Return ONLY valid JSON.
```

```python
import json
from ai_pipeline.client import call_gemini_structured
from ai_pipeline.models import EvaluationOutput

SYSTEM_PROMPT = """[paste prompt above]"""


async def evaluate_session(session_context: dict) -> dict:
    result = await call_gemini_structured(
        system_prompt=SYSTEM_PROMPT,
        user_message=json.dumps(session_context, default=str),
        output_schema=EvaluationOutput,
        stage="evaluation_engine",
    )
    return result.model_dump()
```

---

## Quality Check Before Committing

```bash
cd backend
uv run mypy ai_pipeline/
uv run pytest tests/unit/ -v
grep -rn "sk-\|gsk_\|AIza" ai_pipeline/ || echo "Clean - no secrets"
```

---

## Commit Suggestions

```
feat(ai): add Groq and Gemini clients with structured JSON output and retry logic
feat(ai): add Pydantic output schemas for all six pipeline modules
feat(ai): implement resume parser with skill graph extraction and bluff risk flagging
feat(ai): implement JD analyzer for role requirements and seniority extraction
feat(ai): implement tiered question generator with resume-grounded prompting
feat(ai): implement adaptive follow-up engine with quality-based question branching
feat(ai): implement bluff detector with operational verification question generation
feat(ai): implement evaluation engine using Gemini 1.5 Flash with full session context
```
