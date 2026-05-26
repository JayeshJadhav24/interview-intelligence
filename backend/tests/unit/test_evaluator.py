"""
Unit tests for ai_pipeline/evaluator.py.
Patches _get_chain to avoid real LLM calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_pipeline.evaluator import (
    _build_bluff_summary,
    _build_transcript,
    evaluate_session,
)
from ai_pipeline.schemas import EvaluationReport

SAMPLE_QA = [
    {
        "question": "Explain Python's GIL.",
        "answer": "The GIL prevents true parallelism in CPython.",
        "quality_score": 0.8,
        "is_bluff_detected": False,
    },
    {
        "question": "Describe your experience with Kubernetes.",
        "answer": "I'm an expert in Kubernetes.",
        "quality_score": 0.3,
        "is_bluff_detected": True,
    },
]

SAMPLE_REPORT = EvaluationReport(
    overall_score=0.72,
    technical_score=0.75,
    communication_score=0.80,
    recommendation="maybe",
    strengths="Strong Python fundamentals",
    gaps="Overstated Kubernetes experience",
    bluff_summary="Kubernetes claim unverified",
    full_report="The candidate shows solid Python skills but bluffed on Kubernetes.",
)


class TestBuildTranscript:
    def test_formats_all_questions(self) -> None:
        result = _build_transcript(SAMPLE_QA)
        assert "Q1: Explain Python's GIL." in result
        assert "A1: The GIL prevents true parallelism in CPython." in result
        assert "score: 80%" in result

    def test_marks_bluff_entries(self) -> None:
        result = _build_transcript(SAMPLE_QA)
        assert "[BLUFF DETECTED]" in result

    def test_empty_answer_handled(self) -> None:
        qa = [{"question": "Q?", "answer": "", "quality_score": 0.0, "is_bluff_detected": False}]
        result = _build_transcript(qa)
        assert "score: 0%" in result

    def test_no_bluff_no_marker(self) -> None:
        qa = [
            {
                "question": "Q?",
                "answer": "A",
                "quality_score": 0.5,
                "is_bluff_detected": False,
            }
        ]
        result = _build_transcript(qa)
        assert "[BLUFF DETECTED]" not in result


class TestBuildBluffSummary:
    def test_detects_bluffed_questions(self) -> None:
        result = _build_bluff_summary(SAMPLE_QA)
        assert "Kubernetes" in result

    def test_none_detected_when_clean(self) -> None:
        clean_qa = [{**q, "is_bluff_detected": False} for q in SAMPLE_QA]
        result = _build_bluff_summary(clean_qa)
        assert result == "None detected"


class TestEvaluateSession:
    @pytest.mark.asyncio
    async def test_calls_chain_with_correct_keys(self) -> None:
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=SAMPLE_REPORT)

        with patch("ai_pipeline.evaluator._get_chain", return_value=mock_chain):
            await evaluate_session(
                job_role="Backend Engineer",
                candidate_profile="3 years Python",
                qa_pairs=SAMPLE_QA,
            )

        mock_chain.ainvoke.assert_awaited_once()
        call_kwargs = mock_chain.ainvoke.call_args[0][0]
        assert "candidate_profile" in call_kwargs
        assert "job_role" in call_kwargs
        assert "transcript" in call_kwargs
        assert "bluff_summary" in call_kwargs
        assert "format_instructions" in call_kwargs

    @pytest.mark.asyncio
    async def test_returns_evaluation_report(self) -> None:
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=SAMPLE_REPORT)

        with patch("ai_pipeline.evaluator._get_chain", return_value=mock_chain):
            result = await evaluate_session(
                job_role="Backend Engineer",
                candidate_profile="3 years Python",
                qa_pairs=SAMPLE_QA,
            )

        assert isinstance(result, EvaluationReport)
        assert result.recommendation == "maybe"
        assert result.overall_score == 0.72
