from unittest.mock import AsyncMock, patch

import pytest

from ai_pipeline.resume_parser import extract_text_from_pdf, parse_resume_from_text
from ai_pipeline.schemas import ExtractedSkill, ResumeParseResult


class TestExtractTextFromPdf:
    def test_raises_on_invalid_bytes(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 — fitz raises varied exception types
            extract_text_from_pdf(b"not a pdf")

    def test_returns_string(self) -> None:
        import fitz

        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        result = extract_text_from_pdf(pdf_bytes)
        assert isinstance(result, str)


class TestParseResumeFromText:
    @pytest.mark.asyncio
    async def test_calls_chain_and_returns_result(self) -> None:
        mock_result = ResumeParseResult(
            candidate_name="Alice",
            skills=[
                ExtractedSkill(
                    name="Python",
                    category="backend",
                    confidence_score=0.9,
                    evidence="5 years Python",
                )
            ],
            summary="Experienced developer",
        )
        mock_chain = AsyncMock(ainvoke=AsyncMock(return_value=mock_result))
        with patch("ai_pipeline.resume_parser._get_chain", return_value=mock_chain):
            result = await parse_resume_from_text("Alice has 5 years of Python experience")
        assert result.candidate_name == "Alice"
        assert len(result.skills) == 1
        assert result.skills[0].name == "Python"

    @pytest.mark.asyncio
    async def test_truncates_long_resume(self) -> None:
        """resume_text longer than 12k chars should be capped before being sent."""
        long_text = "x" * 20000
        captured_kwargs: list[dict] = []

        async def mock_ainvoke(kwargs: dict) -> ResumeParseResult:
            captured_kwargs.append(kwargs)
            return ResumeParseResult(skills=[], summary="empty")

        mock_chain = AsyncMock(ainvoke=mock_ainvoke)
        with patch("ai_pipeline.resume_parser._get_chain", return_value=mock_chain):
            await parse_resume_from_text(long_text)

        assert len(captured_kwargs[0]["resume_text"]) <= 12000
