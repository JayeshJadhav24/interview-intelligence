"""
Live interview graph built with LangGraph.

LangGraph concepts used:
  StateGraph     : A directed graph where each node is a function that reads
                   and writes to a shared typed state (InterviewState).
  TypedDict      : Defines the shape of the state passed between nodes.
  Annotated      : Used with operator.add to make list fields append-only
                   (LangGraph "reducer" pattern).
  add_edge       : Unconditional transition between nodes.
  add_conditional_edges : Routes to different nodes based on a classifier
                          function's return value.
  END            : Special LangGraph sentinel — terminates the graph.
  compile()      : Turns the graph definition into a runnable object.

Graph flow:
                     ┌─────────────────┐
                     │  evaluate_answer │
                     └────────┬────────┘
                              │ _route_after_eval()
               ┌──────────────┼──────────────┐
               ▼              ▼              ▼
        [follow_up]    [next_question]     [END]
               │              │
               └──────┬───────┘
                      ▼
               evaluate_answer (loop)
"""

import operator
from typing import Annotated, Any

from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from ai_pipeline.llm_client import get_llm
from ai_pipeline.schemas import AnswerEvaluation

# ── State ─────────────────────────────────────────────────────────────────────


class InterviewState(TypedDict):
    """
    Shared mutable state flowing through the LangGraph.

    Annotated[list, operator.add] is LangGraph's reducer pattern:
    each node appends to the list rather than replacing it.
    """

    session_id: str
    questions: list[dict]  # ordered list of {id, text, type, difficulty}
    current_index: int  # which question we're on
    answers: Annotated[list[dict], operator.add]  # accumulated answers
    evaluations: Annotated[list[dict], operator.add]  # accumulated evaluations
    follow_up_count: int  # follow-ups asked for current question
    max_follow_ups: int  # cap per question (default 2)
    finished: bool


# ── LLM + parser ──────────────────────────────────────────────────────────────

_eval_parser: PydanticOutputParser[AnswerEvaluation] = PydanticOutputParser(
    pydantic_object=AnswerEvaluation
)

_EVAL_SYSTEM = """\
You are a strict technical interviewer evaluating a candidate's answer.
Score honestly — reward depth and specific examples, penalise vagueness.
Return valid JSON matching the schema exactly — no markdown fences."""

_EVAL_HUMAN = """\
Question asked: {question}
Candidate's answer: {answer}

{format_instructions}"""

_eval_prompt = ChatPromptTemplate.from_messages([("system", _EVAL_SYSTEM), ("human", _EVAL_HUMAN)])

_eval_chain = None


def _get_eval_chain():
    global _eval_chain
    if _eval_chain is None:
        _eval_chain = _eval_prompt | get_llm() | _eval_parser
    return _eval_chain


# ── Graph nodes ───────────────────────────────────────────────────────────────


async def evaluate_answer(state: InterviewState) -> dict[str, Any]:
    """
    Node: evaluate the latest answer from the candidate.

    Reads the last item in state["answers"], calls the LLM evaluation chain,
    and appends the result to state["evaluations"].
    """
    latest_answer = state["answers"][-1]
    current_q = state["questions"][state["current_index"]]

    evaluation: AnswerEvaluation = await _get_eval_chain().ainvoke(
        {
            "question": current_q["text"],
            "answer": latest_answer["text"],
            "format_instructions": _eval_parser.get_format_instructions(),
        }
    )

    return {
        "evaluations": [
            {
                "question_id": current_q["id"],
                "quality_score": evaluation.quality_score,
                "is_bluff_detected": evaluation.is_bluff_detected,
                "needs_follow_up": evaluation.needs_follow_up,
                "reasoning": evaluation.reasoning,
                "follow_up_question": evaluation.follow_up_question,
            }
        ]
    }


async def ask_follow_up(state: InterviewState) -> dict[str, Any]:
    """
    Node: inject a follow-up question into the questions list and advance
    the index to it. The follow-up question text comes from the last evaluation.
    """
    last_eval = state["evaluations"][-1]
    follow_up_text = last_eval.get("follow_up_question") or "Can you elaborate further?"

    follow_up_q = {
        "id": f"followup-{state['current_index']}-{state['follow_up_count']}",
        "text": follow_up_text,
        "type": "follow_up",
        "difficulty": "medium",
    }

    # Insert the follow-up right after the current question
    new_questions = list(state["questions"])
    insert_at = state["current_index"] + 1
    new_questions.insert(insert_at, follow_up_q)

    return {
        "questions": new_questions,
        "current_index": insert_at,
        "follow_up_count": state["follow_up_count"] + 1,
    }


async def advance_question(state: InterviewState) -> dict[str, Any]:
    """Node: move to the next question, reset follow-up counter."""
    return {
        "current_index": state["current_index"] + 1,
        "follow_up_count": 0,
    }


# ── Routing logic ─────────────────────────────────────────────────────────────


def _route_after_eval(state: InterviewState) -> str:
    """
    Conditional edge classifier.

    Returns one of three node names (or END) based on the last evaluation:
      - "ask_follow_up"    : answer was vague + follow-up cap not reached
      - "advance_question" : move on (good answer, bluff detected, or cap reached)
      - END                : no more questions
    """
    last_eval = state["evaluations"][-1]
    at_last_question = state["current_index"] >= len(state["questions"]) - 1
    follow_up_cap_reached = state["follow_up_count"] >= state["max_follow_ups"]

    if at_last_question:
        return END  # type: ignore[return-value]

    if last_eval["needs_follow_up"] and not follow_up_cap_reached:
        return "ask_follow_up"

    return "advance_question"


# ── Build the graph ───────────────────────────────────────────────────────────


def build_interview_graph():
    """
    Assemble and compile the LangGraph StateGraph.

    The graph is intentionally stateless at the Python level — all state
    lives in InterviewState and is passed between nodes by LangGraph.
    """
    graph = StateGraph(InterviewState)

    # Register nodes
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("ask_follow_up", ask_follow_up)
    graph.add_node("advance_question", advance_question)

    # Entry point
    graph.set_entry_point("evaluate_answer")

    # Conditional routing after evaluation
    graph.add_conditional_edges(
        "evaluate_answer",
        _route_after_eval,
        {
            "ask_follow_up": "ask_follow_up",
            "advance_question": "advance_question",
            END: END,
        },
    )

    # After inserting a follow-up, go back and evaluate the (not-yet-answered) question
    # The caller must supply the follow-up answer before re-invoking the graph.
    graph.add_edge("ask_follow_up", END)

    # After advancing, the graph ends — caller drives the loop question-by-question
    graph.add_edge("advance_question", END)

    return graph.compile()


# Module-level compiled graph (lazy)
_interview_graph = None


def get_interview_graph():
    global _interview_graph
    if _interview_graph is None:
        _interview_graph = build_interview_graph()
    return _interview_graph
