"""
Question generator using a LangChain LCEL chain.

Chain anatomy:
  ChatPromptTemplate  — fills resume summary + JD requirements + bluff risks
        |
  ChatOpenAI          — calls EPAM Dial (primary model)
        |
  PydanticOutputParser[QuestionBatch]
                      — validates JSON → typed QuestionBatch model

The generator produces three tiers of questions in a single LLM call:

  Tier 1 — Foundation (easy)
    Broad coverage of all claimed skills. Warm-up, confirm baseline.

  Tier 2 — Depth (medium)
    Targets skills that overlap with JD's *required* skills.
    Probes understanding beyond surface-level claims.

  Tier 3 — Verification (hard)
    Targets skills marked is_bluff_risk=True.
    Operational questions: "show me you actually used this in production."
"""

from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ai_pipeline.llm_client import get_llm
from ai_pipeline.schemas import JDAnalysisResult, QuestionBatch, ResumeParseResult

_SYSTEM = """\
You are a senior technical interviewer preparing for a realistic interview.
Your goal is to simulate real interviewer flow:
1. Start broad and resume-grounded (warm-up)
2. Move into core technical evaluation
3. Deep-dive into architecture and trade-offs
4. Add scenario-based problem solving
5. Include behavioral and bluff-validation checks

Questions must feel connected, progressive, and context-aware.
Avoid abrupt topic jumps.

Return valid JSON matching the schema exactly — no markdown fences."""

_HUMAN = """\
Generate a structured set of interview questions based on the following context.

=== CANDIDATE PROFILE ===
Name: {candidate_name}
Total Experience: {total_experience_years} years
Summary: {resume_summary}

Top Skills (from resume):
{skills_summary}

Bluff Risk Skills (claimed but evidence is thin):
{bluff_risks}

=== ROLE REQUIREMENTS ===
Job Title: {job_title}
Seniority: {seniority_level}
Required Skills: {required_skills}

=== INSTRUCTIONS ===
Generate exactly {total_questions} questions in this flow order:
- {foundation_count} Warm-up/Foundation questions (difficulty=easy, question_type=conceptual)
- {depth_count} Core + Deep technical questions (difficulty=medium or hard,
  question_type=practical or conceptual)
- {behavioral_count} Behavioral question (difficulty=medium, question_type=behavioral)
- {verification_count} Bluff-check questions (difficulty=hard, question_type=bluff_check)

Question type MUST be one of: conceptual | practical | behavioral | bluff_check
Difficulty MUST be one of: easy | medium | hard

Ensure each later question naturally builds on candidate context
(resume/JD/projects) rather than being random.

For each question include the skill_name it targets and a brief rationale.

{format_instructions}"""

# ── Parser + LCEL chain ───────────────────────────────────────────────────────
_parser: PydanticOutputParser[QuestionBatch] = PydanticOutputParser(pydantic_object=QuestionBatch)
_prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

# Lazy chain — avoids API key validation at import time
_question_chain = None


def _get_chain():
    global _question_chain
    if _question_chain is None:
        _question_chain = _prompt | get_llm() | _parser
    return _question_chain


def _build_skills_summary(resume: ResumeParseResult) -> str:
    lines = []
    for skill in resume.skills[:15]:  # top 15 skills
        bluff = " ⚠ bluff risk" if skill.is_bluff_risk else ""
        yoe = f" ({skill.years_experience}y)" if skill.years_experience else ""
        lines.append(f"  - {skill.name}{yoe} [{skill.category}]{bluff}")
    return "\n".join(lines) or "  (none extracted)"


def _build_required_skills(jd: JDAnalysisResult) -> str:
    lines = []
    for req in jd.required_skills[:10]:
        years = f", min {req.min_years}y" if req.min_years else ""
        lines.append(f"  - {req.skill} [{req.importance}{years}]")
    return "\n".join(lines) or "  (none specified)"


async def generate_questions(
    resume: ResumeParseResult,
    jd: JDAnalysisResult,
    foundation_count: int = 2,
    depth_count: int = 5,
    behavioral_count: int = 1,
    verification_count: int = 2,
) -> QuestionBatch:
    """
    Invoke the LCEL question-generation chain.

    Default: 10 questions total (2 warm-up + 5 core/deep + 1 behavioral + up to 2 bluff-check).
    Verification count is capped at the number of bluff-risk skills found.
    """
    bluff_risks = resume.bluff_risk_flags or [s.name for s in resume.skills if s.is_bluff_risk]
    # Don't ask more verification questions than there are bluff risks
    verification_count = min(verification_count, len(bluff_risks)) if bluff_risks else 0
    total = foundation_count + depth_count + behavioral_count + verification_count

    return await _get_chain().ainvoke(
        {
            "candidate_name": resume.candidate_name or "Candidate",
            "total_experience_years": resume.total_experience_years or "unknown",
            "resume_summary": resume.summary,
            "skills_summary": _build_skills_summary(resume),
            "bluff_risks": ", ".join(bluff_risks) if bluff_risks else "none identified",
            "job_title": jd.job_title,
            "seniority_level": jd.seniority_level,
            "required_skills": _build_required_skills(jd),
            "total_questions": total,
            "foundation_count": foundation_count,
            "depth_count": depth_count,
            "behavioral_count": behavioral_count,
            "verification_count": verification_count,
            "format_instructions": _parser.get_format_instructions(),
        }
    )
