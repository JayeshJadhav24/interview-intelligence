import pytest
from pydantic import ValidationError

from ai_pipeline.schemas import ExtractedSkill, JDAnalysisResult, ResumeParseResult, RoleRequirement


class TestExtractedSkill:
    def test_valid_skill(self) -> None:
        skill = ExtractedSkill(
            name="Python",
            category="backend",
            confidence_score=0.9,
            evidence="5 years of Python development",
        )
        assert skill.name == "Python"
        assert skill.is_bluff_risk is False

    def test_confidence_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedSkill(name="X", category="backend", confidence_score=1.5, evidence="test")

    def test_confidence_score_lower_bound(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedSkill(name="X", category="backend", confidence_score=-0.1, evidence="test")


class TestResumeParseResult:
    def test_empty_skills_list(self) -> None:
        result = ResumeParseResult(skills=[], summary="No skills found")
        assert result.skills == []
        assert result.bluff_risk_flags == []

    def test_with_skills(self) -> None:
        skill = ExtractedSkill(
            name="FastAPI", category="backend", confidence_score=0.8, evidence="Built REST APIs"
        )
        result = ResumeParseResult(
            candidate_name="Jane Doe",
            total_experience_years=3.0,
            skills=[skill],
            summary="Backend developer",
        )
        assert len(result.skills) == 1
        assert result.candidate_name == "Jane Doe"


class TestJDAnalysisResult:
    def test_valid_jd_result(self) -> None:
        req = RoleRequirement(skill="Python", category="backend", importance="required")
        result = JDAnalysisResult(
            job_title="Backend Engineer",
            seniority_level="mid",
            required_skills=[req],
            key_responsibilities=["Build APIs"],
            summary="Mid-level backend role",
        )
        assert result.seniority_level == "mid"
        assert len(result.required_skills) == 1
