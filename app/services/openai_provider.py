"""Opt-in Responses API adapter. No automatic retries or cross-provider fallbacks."""
from types import SimpleNamespace

import requests

from app import config
from app.services import model_usage


def generate(prompt: str, model: str, max_tokens: int, *, images=None, system=""):
    if model not in {"gpt-6-luna", "gpt-6.1-sol"}:
        raise ValueError("This test supports gpt-6-luna or gpt-6.1-sol; add verified cost rates before another model")
    if not config.OPENAI_API_KEY:
        raise ValueError("OpenAI is selected but OPENAI_API_KEY is not configured on the server")
    content = []
    for image in images or []:
        source = image["source"]
        content.append({
            "type": "input_image",
            "image_url": f"data:{source['media_type']};base64,{source['data']}",
            "detail": "high",
        })
    content.append({"type": "input_text", "text": prompt})
    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": max_tokens,
        "reasoning": {"effort": "none"},
        "text": {"format": {"type": "json_object"}},
        "store": False,
    }
    if system:
        payload["instructions"] = system
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses", json=payload,
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            timeout=(10, 100),
        )
    except Exception as exc:
        model_usage.record(model, "openai", error=exc)
        raise
    if response.status_code >= 400:
        model_usage.record(model, "openai", error=ValueError())
        # Never relay request headers, a key, or the provider's full response.
        raise ValueError(f"OpenAI request failed (HTTP {response.status_code}); check model access and account billing")
    body = response.json()
    usage = body.get("usage") or {}
    if not usage or "input_tokens" not in usage or "output_tokens" not in usage:
        model_usage.record(model, "openai", stop_reason=body.get("status"))
        raise ValueError("OpenAI response omitted token usage; cannot record this test reliably")
    model_usage.record(model, "openai", usage=SimpleNamespace(**usage), stop_reason=body.get("status"))
    text = "".join(
        block.get("text", "")
        for output in body.get("output", []) if output.get("type") == "message"
        for block in output.get("content", []) if block.get("type") == "output_text"
    )
    if body.get("status") != "completed" or not text:
        raise ValueError("OpenAI response was incomplete or refused; review the photos before retrying")
    # Match the existing writer response shape without introducing SDK coupling.
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)], stop_reason="end_turn", model=model,
        usage=SimpleNamespace(
            input_tokens=int(usage["input_tokens"]),
            output_tokens=int(usage["output_tokens"]),
        ),
    )
