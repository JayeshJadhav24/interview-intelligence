"""
LLM client built on LangChain's ChatOpenAI.

Key concepts used:
  - ChatOpenAI       : LangChain's async-capable wrapper around OpenAI chat models.
                       Pointed at EPAM Dial (OpenAI-compatible base URL).
  - PromptTemplate   : Parameterised prompt strings; rendered via .format_messages().
  - JsonOutputParser : Parses the model's JSON string into a dict, then we
                       validate it with Pydantic for strict type safety.
  - LCEL (|)         : pipe operator — composes Runnable objects into a chain.
                       Each step's output becomes the next step's input.
"""

from typing import TypeVar

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

ResponseT = TypeVar("ResponseT", bound=BaseModel)

_llm: ChatOpenAI | None = None


def get_llm(model: str | None = None) -> ChatOpenAI:
    """Return a cached ChatOpenAI instance pointed at EPAM Dial."""
    global _llm
    settings = get_settings()
    chosen_model = model or settings.primary_model
    if _llm is None or _llm.model_name != chosen_model:
        _llm = ChatOpenAI(
            model=chosen_model,
            openai_api_key=settings.dial_api_key,  # type: ignore[arg-type]
            openai_api_base=settings.dial_api_base_url,
            temperature=0.2,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _llm


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def structured_completion(
    prompt: str,
    system: str,
    response_schema: type[ResponseT],
    model: str | None = None,
) -> ResponseT:
    """
    Single structured LLM call using an LCEL chain:

        ChatPromptTemplate | ChatOpenAI | JsonOutputParser

    The chain is invoked with ainvoke() for async execution.
    Output is then validated by the caller's Pydantic schema.
    """
    llm = get_llm(model)

    # Build a two-message prompt: system context + user content
    chat_prompt = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{prompt}")])

    # LCEL chain: prompt → llm → parse JSON to dict
    chain = chat_prompt | llm | JsonOutputParser()

    data: dict = await chain.ainvoke({"system": system, "prompt": prompt})  # type: ignore[assignment]
    return response_schema.model_validate(data)
