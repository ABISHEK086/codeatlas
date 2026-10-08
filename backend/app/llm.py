import time

import httpx

from .config import settings

URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(Exception):
    pass


def _retry_after(r: httpx.Response) -> float:
    try:
        return min(float(r.headers.get("retry-after", 5)), 20.0)
    except ValueError:
        return 5.0


def chat(messages: list[dict], tools: list[dict] | None = None,
         json_mode: bool = False, temperature: float = 0.1,
         max_tokens: int = 1500) -> dict:
    """Returns the assistant message dict. Swap this one function to change provider."""
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set in .env")

    payload: dict = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens + 2000,   # reasoning models spend tokens thinking
    }
    if "gpt-oss" in settings.groq_model:
        payload["reasoning_effort"] = "low"   # faster, and fewer tokens used
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    for attempt in range(3):
        try:
            r = httpx.post(URL, headers=headers, json=payload, timeout=60)
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach Groq: {e}")
        if r.status_code == 429 and attempt < 2:      # free-tier rate limit: wait, retry
            time.sleep(_retry_after(r))
            continue
        if r.status_code >= 400:
            raise LLMError(f"Groq error {r.status_code}: {r.text[:400]}")
        return r.json()["choices"][0]["message"]
    raise LLMError("Groq request failed")