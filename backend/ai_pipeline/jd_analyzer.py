"""
JD analyzer using a LangChain LCEL chain.

Chain anatomy (same pattern as resume_parser):
  ChatPromptTemplate  — fills {jd_text} into the prompt
        |
  ChatOpenAI          — calls EPAM Dial
        |
  PydanticOutputParser[JDAnalysisResult]
                      — validates JSON → typed Pydantic model
"""

from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ai_pipeline.llm_client import get_llm
from ai_pipeline.schemas import JDAnalysisResult

_SYSTEM = """\
You are an expert technical recruiter.
Analyze the job description and extract structured role requirements.
Return valid JSON matching the schema exactly — no markdown fences."""

_HUMAN = """\
Analyze this job description and extract all role requirements.

Job Description:
---
{jd_text}
---

{format_instructions}"""

# ── Parser + LCEL chain ───────────────────────────────────────────────────────
_parser: PydanticOutputParser[JDAnalysisResult] = PydanticOutputParser(
    pydantic_object=JDAnalysisResult
)
_prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

# Lazy chain — avoids API key validation at import time
_jd_chain = None


def _get_chain():
    global _jd_chain
    if _jd_chain is None:
        _jd_chain = _prompt | get_llm() | _parser
    return _jd_chain


async def analyze_jd(jd_text: str) -> JDAnalysisResult:
    """Invoke the LCEL chain asynchronously."""
    return await _get_chain().ainvoke(
        {
            "jd_text": jd_text[:8000],
            "format_instructions": _parser.get_format_instructions(),
        }
    )
