"""Provider-agnostic structured LLM calls.

Both providers are asked to return an instance of a Pydantic schema. Anthropic
uses `messages.parse` (structured outputs); Gemini uses `response_schema`.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from .config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMTimeoutError(RuntimeError):
    """Raised when the LLM request exceeds the configured timeout."""


def parse_structured(
    settings: Settings,
    system: str,
    user: str,
    schema: type[T],
    max_tokens: int = 4096,
    effort: str | None = None,
) -> T:
    """Run a structured completion and return a validated `schema` instance.

    `effort` overrides the provider's default reasoning effort for this call.
    """
    effort = effort or settings.effort
    if settings.provider == "gemini":
        result = _gemini_parse(settings, system, user, schema)
    else:
        result = _anthropic_parse(settings, system, user, schema, max_tokens, effort)
    if result is None:
        raise RuntimeError(
            f"{settings.provider} returned no structured output for {schema.__name__}."
        )
    return result


def _anthropic_parse(
    settings: Settings, system: str, user: str, schema: type[T], max_tokens: int, effort: str
) -> T | None:
    import anthropic

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.timeout,
        max_retries=2,
    )
    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            output_config={"effort": effort},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
    except anthropic.APITimeoutError as exc:
        raise LLMTimeoutError(
            f"Anthropic request timed out after {settings.timeout:g}s. "
            "Try fewer companies (--max-companies), a lighter model, or raise RJF_TIMEOUT."
        ) from exc
    return response.parsed_output


def _gemini_parse(settings: Settings, system: str, user: str, schema: type[T]) -> T | None:
    from google import genai

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options={"timeout": int(settings.timeout * 1000)},  # milliseconds
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user,
        config={
            "system_instruction": system,
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    # google-genai validates and returns the pydantic instance on `.parsed`.
    parsed = response.parsed
    if isinstance(parsed, schema):
        return parsed
    if isinstance(parsed, dict):
        return schema.model_validate(parsed)
    return None
