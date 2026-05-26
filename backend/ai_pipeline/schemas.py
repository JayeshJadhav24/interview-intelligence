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
