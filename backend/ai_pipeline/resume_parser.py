"""
Resume parser using a LangChain LCEL chain.

Chain anatomy:
  ChatPromptTemplate  — fills {resume_text} into the prompt messages
        |
  ChatOpenAI (via get_llm())  — calls EPAM Dial, returns an AIMessage
        |
  PydanticOutputParser[ResumeParseResult]
                      — parses the JSON string inside AIMessage.content
                        and validates it into a typed Pydantic model

The chain is assembled once (_resume_chain) and reused across calls.
ainvoke() drives the async execution end-to-end.
"""

import io

import fitz  # PyMuPDF
from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ai_pipeline.llm_client import get_llm
from ai_pipeline.schemas import ResumeParseResult

_SYSTEM = """\
You are an expert technical recruiter and resume analyst.
Extract a structured skill graph from the resume text provided.
Return valid JSON matching the schema exactly — no markdown fences.
Be conservative with confidence scores (0.9+ only with clear evidence).
Flag is_bluff_risk=true if a skill is claimed at senior level but evidence is thin."""

_HUMAN = """\
Analyze this resume and extract all technical and soft skills.

Resume text:
---
{resume_text}
---

{format_instructions}"""

# ── Parser ────────────────────────────────────────────────────────────────────
_parser: PydanticOutputParser[ResumeParseResult] = PydanticOutputParser(
    pydantic_object=ResumeParseResult
)

_prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

# Chain is built lazily on first call so the LLM client (which validates
# DIAL_API_KEY at instantiation) is not created at import time.
_resume_chain = None


def _get_chain():
    global _resume_chain
    if _resume_chain is None:
        _resume_chain = _prompt | get_llm() | _parser
    return _resume_chain


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages).strip()


async def parse_resume(pdf_bytes: bytes) -> ResumeParseResult:
    resume_text = extract_text_from_pdf(pdf_bytes)
    return await parse_resume_from_text(resume_text)


async def parse_resume_from_text(resume_text: str) -> ResumeParseResult:
    """Invoke the LCEL chain asynchronously."""
    return await _get_chain().ainvoke(
        {
            "resume_text": resume_text[:12000],
            "format_instructions": _parser.get_format_instructions(),
        }
    )
