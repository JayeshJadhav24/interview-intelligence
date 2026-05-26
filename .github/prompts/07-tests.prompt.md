---
mode: agent
description: >
  Writes all tests for the Interview Intelligence System: pytest unit tests with
  LLM mocking, FastAPI integration tests with TestClient, conftest.py fixtures,
  PDF edge case tests, and coverage verification. Shows every test file before
  creating it. Asks which component to test first.
tools:
  - codebase
  - editFiles
  - runCommand
  - terminalLastCommand
---

# Tests Agent

You write tests that catch real bugs. You test behavior, not implementation.
Show every test file before writing it. Never mock things that don't need mocking.

---

## Opening Questions

```
1. "Which component needs tests?
   A) AI pipeline unit tests (LLM calls mocked)
   B) FastAPI API integration tests
   C) Service layer unit tests
   D) PDF service edge cases
   E) conftest.py fixtures setup"

2. "Run existing tests first to see coverage baseline?
   cd backend && uv run pytest tests/ --cov=app --cov=ai_pipeline -q"

3. "Show test file before creating? (yes — always)"
```

---

## `backend/tests/conftest.py`

```python
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.main import app
from app.database import Base, get_db
from app.config import get_settings

settings = get_settings()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    TestSession = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(mocker) -> dict:
    mocker.patch(
        "app.dependencies.verify_supabase_jwt",
        return_value={"id": "00000000-0000-0000-0000-000000000001",
                      "email": "test@example.com"},
    )
    return {"Authorization": "Bearer fake-test-token"}


@pytest.fixture
def sample_resume_text() -> str:
    return """
    Jane Smith — Backend Engineer, 3 years experience

    TechCorp (2022–2024):
    Built REST API with FastAPI serving 50k requests/day
    Containerized with Docker, deployed to AWS ECS
    Implemented JWT auth with refresh token rotation

    Side project (2023):
    Built RAG chatbot using LangChain and ChromaDB
    Chunked PDFs and stored embeddings in ChromaDB

    SKILLS: Python, FastAPI, Docker, PostgreSQL, LangChain, Kubernetes, React
    """.strip()


@pytest.fixture
def valid_skill_graph() -> dict:
    return {
        "candidate_name": "Jane Smith",
        "total_experience_years": 3.0,
        "skills": [
            {
                "skill_name": "FastAPI",
                "category": "backend",
                "level": "advanced",
                "confidence": 0.9,
                "evidence": ["Built REST API with FastAPI serving 50k requests/day"],
                "bluff_risk": False,
                "bluff_reason": None,
            },
            {
                "skill_name": "Kubernetes",
                "category": "devops",
                "level": "intermediate",
                "confidence": 0.2,
                "evidence": ["SKILLS: Kubernetes"],
                "bluff_risk": True,
                "bluff_reason": "Listed in skills section only — no project uses it",
            },
        ],
    }
```

---

## `backend/tests/unit/test_resume_parser.py`

```python
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from ai_pipeline.resume_parser import parse_resume

VALID_JSON = json.dumps({
    "candidate_name": "Jane Smith",
    "total_experience_years": 3.0,
    "skills": [{
        "skill_name": "FastAPI", "category": "backend", "level": "advanced",
        "confidence": 0.9, "evidence": ["Built REST API with FastAPI"],
        "bluff_risk": False, "bluff_reason": None,
    }],
})


def _mock_groq_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.choices[0].message.content = content
    return mock


@pytest.mark.asyncio
async def test_parse_resume_returns_valid_skill_graph(sample_resume_text):
    with patch("ai_pipeline.client.groq_client.chat.completions.create",
               new_callable=AsyncMock, return_value=_mock_groq_response(VALID_JSON)):
        result = await parse_resume(sample_resume_text)

    assert result["candidate_name"] == "Jane Smith"
    assert len(result["skills"]) == 1
    assert result["skills"][0]["skill_name"] == "FastAPI"


@pytest.mark.asyncio
async def test_parse_resume_retries_on_invalid_json(sample_resume_text):
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        content = "not valid json {{" if call_count == 1 else VALID_JSON
        return _mock_groq_response(content)

    with patch("ai_pipeline.client.groq_client.chat.completions.create",
               side_effect=side_effect):
        result = await parse_resume(sample_resume_text)

    assert call_count == 2
    assert result["candidate_name"] == "Jane Smith"


@pytest.mark.asyncio
async def test_parse_resume_raises_pipeline_error_after_two_failures(sample_resume_text):
    from app.exceptions import PipelineError
    with patch("ai_pipeline.client.groq_client.chat.completions.create",
               new_callable=AsyncMock,
               return_value=_mock_groq_response("still not json")):
        with pytest.raises(PipelineError) as exc:
            await parse_resume(sample_resume_text)
    assert "resume_parser" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_parse_resume_bluff_risk_flag(sample_resume_text):
    bluff_json = VALID_JSON.replace('"bluff_risk": false', '"bluff_risk": true')
    with patch("ai_pipeline.client.groq_client.chat.completions.create",
               new_callable=AsyncMock,
               return_value=_mock_groq_response(bluff_json)):
        result = await parse_resume(sample_resume_text)
    assert result["skills"][0]["bluff_risk"] is True
```

---

## `backend/tests/unit/test_followup_engine.py`

```python
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from ai_pipeline.followup_engine import generate_follow_up


def _mock(content: str) -> MagicMock:
    m = MagicMock()
    m.choices[0].message.content = content
    return m


@pytest.mark.asyncio
@pytest.mark.parametrize("quality,expected_direction", [
    ("strong", "harder"),
    ("adequate", "lateral"),
    ("weak", "simpler"),
])
async def test_follow_up_direction_matches_quality(quality, expected_direction):
    response = json.dumps({
        "follow_up_question": "Test follow-up question here",
        "reasoning": "Because the answer was " + quality,
        "escalation_direction": expected_direction,
    })
    with patch("ai_pipeline.client.groq_client.chat.completions.create",
               new_callable=AsyncMock, return_value=_mock(response)):
        result = await generate_follow_up(
            original_question="Explain FastAPI",
            candidate_answer="I used it in a project",
            quality=quality,
            skill_context="FastAPI",
        )
    assert result["escalation_direction"] == expected_direction
    assert len(result["follow_up_question"]) > 5
```

---

## `backend/tests/integration/test_sessions_api.py`

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_session_requires_auth(client: AsyncClient):
    response = await client.post(
        "/sessions",
        data={"candidate_name": "Jane", "job_title": "SWE",
              "jd_text": "Build backend services"},
        files={"resume_file": ("r.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_nonexistent_session_returns_404(client, auth_headers):
    response = await client.get(
        "/sessions/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_empty_on_fresh_user(client, auth_headers):
    response = await client.get("/sessions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["sessions"] == []
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_session_rejects_oversized_file(client, auth_headers, mocker):
    mocker.patch("app.services.session_service.parse_resume",
                 return_value={"candidate_name": "Jane",
                               "total_experience_years": 1, "skills": []})
    mocker.patch("app.services.storage_service.StorageService.upload_resume",
                 return_value="resumes/test.pdf")

    import io
    large_file = io.BytesIO(b"x" * (6 * 1024 * 1024))
    response = await client.post(
        "/sessions",
        data={"candidate_name": "Jane", "job_title": "SWE",
              "jd_text": "Build scalable Python services"},
        files={"resume_file": ("r.pdf", large_file, "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 413
```

---

## `backend/tests/unit/test_pdf_service.py`

```python
from pathlib import Path
import pytest
from app.services.pdf_service import PDFService
from app.exceptions import FileTooLargeError

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_extract_text_from_valid_pdf():
    service = PDFService()
    pdf_bytes = (FIXTURES / "sample_resume.pdf").read_bytes()
    text = service.extract_text(pdf_bytes)
    assert isinstance(text, str)
    assert len(text) > 50


def test_extract_text_returns_empty_string_for_image_only_pdf():
    service = PDFService()
    text = service.extract_text(b"%PDF-1.4\n%%EOF")
    assert isinstance(text, str)


def test_extract_text_raises_for_oversized_file():
    service = PDFService()
    with pytest.raises(FileTooLargeError):
        service.extract_text(b"x" * (6 * 1024 * 1024))
```

---

## Running Tests

Show command, ask "Run this?":

```bash
cd backend

# All tests + coverage
uv run pytest tests/ -v --cov=app --cov=ai_pipeline --cov-report=term-missing

# Fast unit-only (no DB needed)
uv run pytest tests/unit/ -v

# Specific test
uv run pytest tests/unit/test_resume_parser.py::test_parse_resume_retries_on_invalid_json -v

# Coverage threshold check
uv run pytest --cov=app --cov=ai_pipeline --cov-fail-under=70
```

---

## Coverage Targets

```
Overall:            ≥ 70%
app/services/:      ≥ 80%
ai_pipeline/:       ≥ 75%
app/routers/:       ≥ 65%
app/repositories/:  ≥ 60%
```

If below target, show the developer which files are under-covered and suggest tests.

---

## Commit Suggestions

```
test(backend): add pytest conftest with async DB fixtures and auth mock
test(ai): add unit tests for resume parser including retry and validation scenarios
test(ai): add parametrized tests for adaptive follow-up quality branching
test(backend): add session API integration tests for auth, 404, and file size
test(backend): add PDF service tests for oversized files and scanned PDFs
```
