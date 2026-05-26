"""
Unit tests for ai_pipeline/question_generator.py

Key things verified:
- generate_questions() calls the LCEL chain and returns a QuestionBatch
- verification_count is capped at the number of bluff-risk skills
- zero bluff risks → zero verification questions
"""

from unittest.mock import AsyncMock, patch

import pytest

from ai_pipeline.question_generator import generate_questions
from ai_pipeline.schemas import (
    ExtractedSkill,
    GeneratedQuestion,
    JDAnalysisResult,
    QuestionBatch,
    ResumeParseResult,
    RoleRequirement,
)


def _make_resume(bluff_risks: list[str] | None = None) -> ResumeParseResult:
    bluff_risks = bluff_risks or []
    skills = [
        ExtractedSkill(
            name="Python",
            category="backend",
            confidence_score=0.9,
            evidence="5 years Python",
        ),
        ExtractedSkill(
            name="Kubernetes",
            category="devops",
            confidence_score=0.5,
            is_bluff_risk=bool(bluff_risks),
            evidence="mentioned once",
        ),
    ]
    return ResumeParseResult(
        candidate_name="Alice",
        total_experience_years=5,
        skills=skills,
        bluff_risk_flags=bluff_risks,
        summary="Experienced backend developer",
    )


def _make_jd() -> JDAnalysisResult:
    return JDAnalysisResult(
        job_title="Senior Python Engineer",
        seniority_level="senior",
        required_skills=[
            RoleRequirement(skill="Python", category="backend", importance="required"),
            RoleRequirement(skill="Docker", category="devops", importance="preferred"),
        ],
        key_responsibilities=["Build APIs", "Design systems"],
        summary="Senior Python role",
    )


def _make_batch(n: int = 5) -> QuestionBatch:
    questions = [
        GeneratedQuestion(
            text=f"Question {i}?",
            skill_name="Python",
            question_type="technical",
            difficulty="easy",
            rationale="covers Python",
        )
        for i in range(n)
    ]
    return QuestionBatch(questions=questions, total_count=n)


class TestGenerateQuestions:
    @pytest.mark.asyncio
    async def test_returns_question_batch(self) -> None:
        batch = _make_batch(8)
        mock_chain = AsyncMock(ainvoke=AsyncMock(return_value=batch))
        with patch("ai_pipeline.question_generator._get_chain", return_value=mock_chain):
            result = await generate_questions(_make_resume(), _make_jd())
        assert isinstance(result, QuestionBatch)
        assert result.total_count == 8

    @pytest.mark.asyncio
    async def test_verification_capped_at_bluff_count(self) -> None:
        """With 1 bluff risk, verification_count should be capped at 1."""
        batch = _make_batch(9)
        captured_kwargs: list[dict] = []

        async def mock_ainvoke(kwargs: dict) -> QuestionBatch:
            captured_kwargs.append(kwargs)
            return batch

        mock_chain = AsyncMock(ainvoke=mock_ainvoke)
        with patch("ai_pipeline.question_generator._get_chain", return_value=mock_chain):
            await generate_questions(
                _make_resume(bluff_risks=["Kubernetes"]),
                _make_jd(),
                verification_count=2,  # asked for 2 but only 1 bluff risk
            )

        assert captured_kwargs[0]["verification_count"] == 1

    @pytest.mark.asyncio
    async def test_zero_verification_when_no_bluff_risks(self) -> None:
        batch = _make_batch(8)
        captured_kwargs: list[dict] = []

        async def mock_ainvoke(kwargs: dict) -> QuestionBatch:
            captured_kwargs.append(kwargs)
            return batch

        mock_chain = AsyncMock(ainvoke=mock_ainvoke)
        with patch("ai_pipeline.question_generator._get_chain", return_value=mock_chain):
            await generate_questions(_make_resume(bluff_risks=[]), _make_jd())

        assert captured_kwargs[0]["verification_count"] == 0
