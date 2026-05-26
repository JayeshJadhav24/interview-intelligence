import json
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

ResponseT = TypeVar("ResponseT", bound=BaseModel)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(
            api_key=settings.dial_api_key,
            base_url=settings.dial_api_base_url,
        )
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def structured_completion(
    prompt: str,
    system: str,
    response_schema: type[ResponseT],
    model: str | None = None,
) -> ResponseT:
    settings = get_settings()
    chosen_model = model or settings.primary_model
    client = get_client()

    response = await client.chat.completions.create(
        model=chosen_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    return response_schema.model_validate(data)
