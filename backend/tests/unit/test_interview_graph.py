"""
Unit tests for ai_pipeline/interview_graph.py

Tests cover:
  - evaluate_answer node: calls LLM chain, stores evaluation in state
  - ask_follow_up node: inserts follow-up question, advances index
  - advance_question node: increments index, resets follow_up_count
  - _route_after_eval: routing logic for all branches
"""

from unittest.mock import AsyncMock, patch

import pytest

from ai_pipeline.interview_graph import (
    InterviewState,
    _route_after_eval,
    advance_question,
    ask_follow_up,
    evaluate_answer,
)
from ai_pipeline.schemas import AnswerEvaluation


def _base_state(**overrides) -> InterviewState:
    state: InterviewState = {
        "session_id": "session-1",
        "questions": [
            {
                "id": "q1",
                "text": "Explain Python's GIL.",
                "type": "technical",
                "difficulty": "medium",
            },
            {
                "id": "q2",
                "text": "Describe async/await.",
                "type": "technical",
                "difficulty": "medium",
            },
        ],
        "current_index": 0,
        "answers": [{"text": "The GIL is a mutex that prevents multiple threads."}],
        "evaluations": [],
        "follow_up_count": 0,
        "max_follow_ups": 2,
        "finished": False,
    }
    state.update(overrides)  # type: ignore[arg-type]
    return state


class TestEvaluateAnswerNode:
    @pytest.mark.asyncio
    async def test_appends_evaluation_to_state(self) -> None:
        mock_eval = AnswerEvaluation(
            quality_score=0.8,
            is_bluff_detected=False,
            needs_follow_up=False,
            reasoning="Good answer with specific detail.",
            follow_up_question=None,
        )
        mock_chain = AsyncMock(ainvoke=AsyncMock(return_value=mock_eval))
        with patch("ai_pipeline.interview_graph._get_eval_chain", return_value=mock_chain):
            result = await evaluate_answer(_base_state())

        assert len(result["evaluations"]) == 1
        ev = result["evaluations"][0]
        assert ev["quality_score"] == 0.8
        assert ev["is_bluff_detected"] is False
        assert ev["question_id"] == "q1"

    @pytest.mark.asyncio
    async def test_bluff_detected_stored(self) -> None:
        mock_eval = AnswerEvaluation(
            quality_score=0.2,
            is_bluff_detected=True,
            needs_follow_up=False,
            reasoning="Candidate clearly did not understand.",
        )
        mock_chain = AsyncMock(ainvoke=AsyncMock(return_value=mock_eval))
        with patch("ai_pipeline.interview_graph._get_eval_chain", return_value=mock_chain):
            result = await evaluate_answer(_base_state())

        assert result["evaluations"][0]["is_bluff_detected"] is True


class TestAskFollowUpNode:
    @pytest.mark.asyncio
    async def test_inserts_follow_up_after_current(self) -> None:
        state = _base_state(
            evaluations=[
                {
                    "question_id": "q1",
                    "quality_score": 0.4,
                    "is_bluff_detected": False,
                    "needs_follow_up": True,
                    "reasoning": "Too vague.",
                    "follow_up_question": "Can you give a concrete example?",
                }
            ]
        )
        result = await ask_follow_up(state)

        # Follow-up inserted at index 1 (after current index 0)
        assert result["current_index"] == 1
        assert result["follow_up_count"] == 1
        assert result["questions"][1]["text"] == "Can you give a concrete example?"
        assert result["questions"][1]["type"] == "follow_up"

    @pytest.mark.asyncio
    async def test_default_text_when_no_follow_up_in_eval(self) -> None:
        state = _base_state(
            evaluations=[
                {
                    "question_id": "q1",
                    "quality_score": 0.3,
                    "is_bluff_detected": False,
                    "needs_follow_up": True,
                    "reasoning": "Vague.",
                    "follow_up_question": None,
                }
            ]
        )
        result = await ask_follow_up(state)
        assert "elaborate" in result["questions"][1]["text"].lower()


class TestAdvanceQuestionNode:
    @pytest.mark.asyncio
    async def test_advances_index_and_resets_follow_up(self) -> None:
        state = _base_state(current_index=1, follow_up_count=2)
        result = await advance_question(state)
        assert result["current_index"] == 2
        assert result["follow_up_count"] == 0


class TestRouteAfterEval:
    def _state_with_eval(self, needs_follow_up: bool, follow_up_count: int = 0) -> InterviewState:
        return _base_state(
            evaluations=[
                {
                    "question_id": "q1",
                    "quality_score": 0.5,
                    "is_bluff_detected": False,
                    "needs_follow_up": needs_follow_up,
                    "reasoning": "test",
                    "follow_up_question": "Why?",
                }
            ],
            follow_up_count=follow_up_count,
        )

    def test_routes_to_follow_up_when_needed(self) -> None:
        state = self._state_with_eval(needs_follow_up=True, follow_up_count=0)
        assert _route_after_eval(state) == "ask_follow_up"

    def test_routes_to_advance_when_good_answer(self) -> None:
        state = self._state_with_eval(needs_follow_up=False)
        assert _route_after_eval(state) == "advance_question"

    def test_routes_to_advance_when_follow_up_cap_reached(self) -> None:
        state = self._state_with_eval(needs_follow_up=True, follow_up_count=2)
        assert _route_after_eval(state) == "advance_question"

    def test_routes_to_end_on_last_question(self) -> None:
        from langgraph.graph import END

        state = self._state_with_eval(needs_follow_up=False)
        state["current_index"] = 1  # last question (len=2, index=1)
        assert _route_after_eval(state) == END
