from pydantic import BaseModel, Field


class ExtractedSkill(BaseModel):
    name: str
    category: str = Field(description="e.g. backend, frontend, database, devops, soft_skill")
    confidence_score: float = Field(ge=0.0, le=1.0)
    years_experience: float | None = None
    is_bluff_risk: bool = False
    evidence: str = Field(description="Quote or context from resume supporting this skill")


class ResumeParseResult(BaseModel):
    candidate_name: str | None = None
    total_experience_years: float | None = None
    skills: list[ExtractedSkill]
    bluff_risk_flags: list[str] = Field(
        default_factory=list,
        description="Skills flagged as potentially exaggerated",
    )
    summary: str = Field(description="2-3 sentence professional summary of the candidate")


class RoleRequirement(BaseModel):
    skill: str
    category: str
    importance: str = Field(description="required | preferred | nice_to_have")
    min_years: float | None = None


class JDAnalysisResult(BaseModel):
    job_title: str
    seniority_level: str = Field(description="junior | mid | senior | lead | principal")
    required_skills: list[RoleRequirement]
    key_responsibilities: list[str]
    summary: str


# ── Question generation schemas ───────────────────────────────────────────────


class GeneratedQuestion(BaseModel):
    """A single interview question produced by the question generator."""

    text: str = Field(description="The full question text to ask the candidate")
    skill_name: str | None = Field(
        default=None,
        description="The skill this question targets (matches ExtractedSkill.name)",
    )
    question_type: str = Field(
        description=("technical | behavioral | situational | " "verification | follow_up")
    )
    difficulty: str = Field(description="easy | medium | hard")
    rationale: str = Field(description="Why this question was chosen given the resume/JD context")


class QuestionBatch(BaseModel):
    """
    Ordered list of questions for one interview session.

    Tiers (in order):
      foundation   — easy, broad coverage of claimed skills
      depth        — medium, probe top/required skills deeply
      verification — hard, expose bluff-risk skills
    """

    questions: list[GeneratedQuestion]
    total_count: int = Field(description="Total number of questions generated")
