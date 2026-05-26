"""
Session evaluator using a LangChain LCEL chain with the eval model (gpt-4o).

Why gpt-4o here:
  The full interview transcript (all Q&A pairs + per-answer LLM scores) is
  assembled into a single large prompt. gpt-4o's 128k context window handles
  this comfortably and produces higher-quality narrative reports than the
  primary model.

Chain anatomy (same LCEL pattern as resume_parser / jd_analyzer):
  ChatPromptTemplate  — fills the full transcript into the prompt
        |
  ChatOpenAI (eval_model=gpt-4o)
        |
  PydanticOutputParser[EvaluationReport]
                      — validates JSON → typed EvaluationReport model
"""

from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ai_pipeline.llm_client import get_llm
from ai_pipeline.schemas import EvaluationReport
from app.config import get_settings

_SYSTEM = """\
You are a senior engineering hiring manager writing a structured evaluation report.
You have just completed a technical interview.
Assess the candidate fairly based solely on the transcript provided.
Return valid JSON matching the schema exactly — no markdown fences."""

_HUMAN = """\
=== CANDIDATE PROFILE ===
{candidate_profile}

=== JOB ROLE ===
{job_role}

=== INTERVIEW TRANSCRIPT ===
{transcript}

=== BLUFF DETECTIONS ===
{bluff_summary}

=== INSTRUCTIONS ===
Score all numeric fields between 0.0 and 1.0.
recommendation must be exactly one of: hire | no_hire | maybe

{format_instructions}"""

# ── Parser + lazy LCEL chain ──────────────────────────────────────────────────
_parser: PydanticOutputParser[EvaluationReport] = PydanticOutputParser(
    pydantic_object=EvaluationReport
)
_prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

_eval_chain = None


def _get_chain():
    global _eval_chain
    if _eval_chain is None:
        # Use the eval model (gpt-4o) for higher-quality narrative reports
        _eval_chain = _prompt | get_llm(model=get_settings().eval_model) | _parser
    return _eval_chain


def _build_transcript(qa_pairs: list[dict]) -> str:
    """
    Format a list of {question, answer, quality_score, is_bluff_detected}
    dicts into a readable transcript string.
    """
    lines = []
    for i, qa in enumerate(qa_pairs, 1):
        score_pct = int(qa.get("quality_score", 0) * 100)
        bluff = " [BLUFF DETECTED]" if qa.get("is_bluff_detected") else ""
        lines.append(f"Q{i}: {qa['question']}")
        lines.append(f"A{i}: {qa['answer']} (score: {score_pct}%{bluff})")
        lines.append("")
    return "\n".join(lines)


def _build_bluff_summary(qa_pairs: list[dict]) -> str:
    bluffs = [qa["question"] for qa in qa_pairs if qa.get("is_bluff_detected")]
    if not bluffs:
        return "None detected"
    return "\n".join(f"  - {q}" for q in bluffs)


async def evaluate_session(
    job_role: str,
    candidate_profile: str,
    qa_pairs: list[dict],
) -> EvaluationReport:
    """
    Generate a full evaluation report for a completed interview session.

    Args:
        job_role: e.g. "Senior Python Engineer"
        candidate_profile: Short summary from the resume parser
        qa_pairs: List of dicts with keys:
                  question, answer, quality_score, is_bluff_detected
    """
    return await _get_chain().ainvoke(
        {
            "candidate_profile": candidate_profile,
            "job_role": job_role,
            "transcript": _build_transcript(qa_pairs),
            "bluff_summary": _build_bluff_summary(qa_pairs),
            "format_instructions": _parser.get_format_instructions(),
        }
    )
