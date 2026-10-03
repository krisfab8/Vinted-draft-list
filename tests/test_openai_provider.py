import json
from unittest.mock import Mock

import pytest

from app import config
from app.services import openai_provider


def test_responses_payload_preserves_images_and_usage(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-placeholder")
    response = Mock(status_code=200)
    response.json.return_value = {
        "status": "completed", "usage": {"input_tokens": 1400, "output_tokens": 100},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"brand":"Barbour"}'}]}],
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(openai_provider.requests, "post", post)
    result = openai_provider.generate(
        "Return JSON", "gpt-6-luna", 2048,
        images=[{"source": {"media_type": "image/jpeg", "data": "YWJj"}}],
    )
    payload = post.call_args.kwargs["json"]
    assert payload["input"][0]["content"][0]["image_url"] == "data:image/jpeg;base64,YWJj"
    assert payload["reasoning"]["effort"] == "none"
    assert payload["store"] is False
    assert result.usage.input_tokens == 1400
    assert json.loads(result.content[0].text)["brand"] == "Barbour"
    assert post.call_count == 1


def test_missing_key_makes_no_request(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    post = Mock()
    monkeypatch.setattr(openai_provider.requests, "post", post)
    with pytest.raises(ValueError, match="not configured"):
        openai_provider.generate("JSON", "gpt-6-luna", 100)
    post.assert_not_called()


@pytest.mark.parametrize("status", ["incomplete", "failed"])
def test_incomplete_output_is_not_silently_repaired(monkeypatch, status):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-placeholder")
    response = Mock(status_code=200)
    response.json.return_value = {"status": status, "usage": {"input_tokens": 10, "output_tokens": 10}, "output": []}
    monkeypatch.setattr(openai_provider.requests, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match="incomplete"):
        openai_provider.generate("JSON", "gpt-6-luna", 100)


def test_provider_error_does_not_echo_response(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-placeholder")
    monkeypatch.setattr(openai_provider.requests, "post", Mock(return_value=Mock(status_code=401)))
    with pytest.raises(ValueError, match="HTTP 401"):
        openai_provider.generate("JSON", "gpt-6-luna", 100)


def test_openai_extraction_does_not_call_anthropic(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app import extractor
    monkeypatch.setattr(extractor, "VISION_PROVIDER", "openai")
    monkeypatch.setattr(extractor, "_load_photos", lambda folder: ([], {}))
    monkeypatch.setattr(extractor, "_extract_claude", Mock(side_effect=AssertionError("Unexpected Anthropic call")))
    monkeypatch.setattr(extractor, "_reread_brand_photo", Mock(side_effect=AssertionError("Unexpected reread")))
    monkeypatch.setattr(extractor, "_reread_material_photo", Mock(side_effect=AssertionError("Unexpected reread")))
    response = SimpleNamespace(content=[SimpleNamespace(text=json.dumps({
        "brand": "Barbour", "brand_confidence": "low", "material_confidence": "low",
        "item_type": "jacket", "materials": ["cotton"], "confidence": .2,
        "low_confidence_fields": ["brand", "materials"],
    }))], usage=SimpleNamespace(input_tokens=1000, output_tokens=200))
    monkeypatch.setattr(openai_provider, "generate", Mock(return_value=response))
    item, usage = extractor.extract(tmp_path)
    assert item["brand"] == "Barbour"
    assert usage["model"] == "gpt-6-luna"
    assert usage["input_tokens"] == 1000
