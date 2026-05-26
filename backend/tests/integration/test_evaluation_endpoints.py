"""
Integration tests for the evaluation report endpoints:
  POST /api/v1/sessions/{id}/evaluate  → 201 EvaluationResponse
  GET  /api/v1/sessions/{id}/evaluation → 200 EvaluationResponse

All AI calls are patched so no real LLM is invoked.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from ai_pipeline.schemas import EvaluationReport

FAKE_REPORT = EvaluationReport(
    overall_score=0.82,
    technical_score=0.85,
    communication_score=0.79,
    recommendation="hire",
    strengths="Strong Python and FastAPI fundamentals",
    gaps="Limited cloud infrastructure experience",
    bluff_summary="None detected",
    full_report="The candidate performed well across technical topics.",
)


async def _signup_and_token(client: AsyncClient, email: str) -> str:
    """Register a user and return the access token."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "password123",  # pragma: allowlist secret
            "full_name": "Eval Tester",
        },
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


async def _create_processed_session(client: AsyncClient, token: str) -> str:
    """Create a session and run /process (with AI calls patched) to get questions."""
    from ai_pipeline.schemas import (
        ExtractedSkill,
        GeneratedQuestion,
        JDAnalysisResult,
        QuestionBatch,
        ResumeParseResult,
        RoleRequirement,
    )

    fake_resume = ResumeParseResult(
        candidate_name="Test Candidate",
        summary="3 years Python backend experience.",
        skills=[
            ExtractedSkill(
                name="Python",
                category="backend",
                confidence_score=0.9,
                evidence="5 years Python on resume",
            )
        ],
    )
    fake_jd = JDAnalysisResult(
        job_title="Backend Engineer",
        seniority_level="mid",
        required_skills=[
            RoleRequirement(skill="Python", category="backend", importance="required")
        ],
        key_responsibilities=["Build REST APIs"],
        summary="Mid-level backend role.",
    )
    fake_questions = QuestionBatch(
        questions=[
            GeneratedQuestion(
                text="Explain Python's GIL.",
                question_type="conceptual",
                difficulty="medium",
                rationale="Core Python knowledge check",
            )
        ],
        total_count=1,
    )

    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await client.post(
        "/api/v1/sessions",
        data={
            "job_role": "Backend Engineer",
            "jd_text": "We need a Python backend engineer.",
            "resume_text": "Python developer with 3 years experience.",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    with (
        patch("ai_pipeline.resume_parser._get_chain") as mock_rp,
        patch("ai_pipeline.jd_analyzer._get_chain") as mock_jd,
        patch("ai_pipeline.question_generator._get_chain") as mock_qg,
    ):
        mock_rp.return_value.ainvoke = AsyncMock(return_value=fake_resume)
        mock_jd.return_value.ainvoke = AsyncMock(return_value=fake_jd)
        mock_qg.return_value.ainvoke = AsyncMock(return_value=fake_questions)

        process_resp = await client.post(f"/api/v1/sessions/{session_id}/process", headers=headers)
        assert process_resp.status_code == 200

    return session_id


class TestEvaluateEndpoint:
    @pytest.mark.asyncio
    async def test_evaluate_returns_201_with_report(self, client: AsyncClient) -> None:
        token = await _signup_and_token(client, "eval_201@example.com")
        session_id = await _create_processed_session(client, token)

        with patch("app.services.evaluation.evaluator.evaluate_session") as mock_eval:
            mock_eval.return_value = FAKE_REPORT

            resp = await client.post(
                f"/api/v1/sessions/{session_id}/evaluate",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["recommendation"] == "hire"
        assert data["overall_score"] == pytest.approx(0.82)
        assert data["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_evaluate_unknown_session_returns_404(self, client: AsyncClient) -> None:
        token = await _signup_and_token(client, "eval_404@example.com")
        resp = await client.post(
            f"/api/v1/sessions/{uuid.uuid4()}/evaluate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_evaluate_another_users_session_returns_403(self, client: AsyncClient) -> None:
        owner_token = await _signup_and_token(client, "eval_owner@example.com")
        attacker_token = await _signup_and_token(client, "eval_attacker@example.com")
        session_id = await _create_processed_session(client, owner_token)

        resp = await client.post(
            f"/api/v1/sessions/{session_id}/evaluate",
            headers={"Authorization": f"Bearer {attacker_token}"},
        )
        assert resp.status_code == 403


class TestGetEvaluationEndpoint:
    @pytest.mark.asyncio
    async def test_get_evaluation_returns_existing_report(self, client: AsyncClient) -> None:
        token = await _signup_and_token(client, "eval_get@example.com")
        session_id = await _create_processed_session(client, token)

        # First create the evaluation
        with patch("app.services.evaluation.evaluator.evaluate_session") as mock_eval:
            mock_eval.return_value = FAKE_REPORT
            await client.post(
                f"/api/v1/sessions/{session_id}/evaluate",
                headers={"Authorization": f"Bearer {token}"},
            )

        # Then retrieve it
        resp = await client.get(
            f"/api/v1/sessions/{session_id}/evaluation",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["recommendation"] == "hire"

    @pytest.mark.asyncio
    async def test_get_evaluation_no_report_returns_404(self, client: AsyncClient) -> None:
        token = await _signup_and_token(client, "eval_get_404@example.com")
        session_id = await _create_processed_session(client, token)

        resp = await client.get(
            f"/api/v1/sessions/{session_id}/evaluation",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
