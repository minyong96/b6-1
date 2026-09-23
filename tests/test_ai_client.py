from unittest.mock import MagicMock, patch

import pytest
import requests

from gitgen.ai_client import AIError, ConfigError, call_ai, get_api_key
from gitgen.prompts import Prompt

PROMPT = Prompt("system rules", "user data")


def _resp(status=200, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.text = text
    if payload is None:
        r.json.side_effect = ValueError("no json")
    else:
        r.json.return_value = payload
    return r


def test_api_key_required():
    with pytest.raises(ConfigError, match="AI_API_KEY"):
        get_api_key()


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", " k ")
    assert get_api_key() == "k"


@patch("gitgen.ai_client.requests.post")
def test_anthropic_request_and_parse(post):
    post.return_value = _resp(payload={
        "model": "claude-haiku-4-5",
        "content": [{"type": "text", "text": '{"title": "feat: x"}'}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })
    res = call_ai("anthropic", "key", "claude-haiku-4-5", PROMPT, 0.3, 400, 30)

    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs
    assert url == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "key"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert kwargs["json"]["system"] == "system rules"
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "user data"}]
    assert kwargs["json"]["temperature"] == 0.3
    assert kwargs["json"]["max_tokens"] == 400
    assert kwargs["timeout"] == (5, 30)
    assert res.text == '{"title": "feat: x"}'
    assert not res.truncated
    assert (res.input_tokens, res.output_tokens) == (10, 5)


@patch("gitgen.ai_client.requests.post")
def test_anthropic_omits_temperature_when_none(post):
    post.return_value = _resp(payload={"content": [{"type": "text", "text": "{}"}], "stop_reason": "end_turn"})
    call_ai("anthropic", "key", "claude-opus-5", PROMPT, None, 400)
    assert "temperature" not in post.call_args.kwargs["json"]


@patch("gitgen.ai_client.requests.post")
def test_anthropic_truncated(post):
    post.return_value = _resp(payload={
        "content": [{"type": "text", "text": '{"title": "fe'}], "stop_reason": "max_tokens",
    })
    assert call_ai("anthropic", "k", "m", PROMPT, 0.3, 10).truncated


@patch("gitgen.ai_client.requests.post")
def test_openai_request_and_parse(post):
    post.return_value = _resp(payload={
        "model": "gpt-4o-mini",
        "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    })
    res = call_ai("openai", "key", "gpt-4o-mini", PROMPT, 0.5, 100)
    kwargs = post.call_args.kwargs
    assert post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer key"
    assert kwargs["json"]["messages"][0] == {"role": "system", "content": "system rules"}
    assert res.truncated
    assert res.input_tokens == 7


@patch("gitgen.ai_client.requests.post")
def test_base_url_override(post, monkeypatch):
    monkeypatch.setenv("AI_API_BASE_URL", "http://localhost:9999/v1/messages")
    post.return_value = _resp(payload={"content": [{"type": "text", "text": "{}"}], "stop_reason": "end_turn"})
    call_ai("anthropic", "k", "m", PROMPT, 0.3, 10)
    assert post.call_args.args[0] == "http://localhost:9999/v1/messages"


@pytest.mark.parametrize("status, fragment", [
    (400, "잘못된 요청"), (401, "인증에 실패"), (403, "권한"), (404, "모델을 찾을 수 없"),
    (429, "한도"), (500, "서버 측 오류"), (529, "서버 측 오류"),
])
@patch("gitgen.ai_client.requests.post")
def test_http_errors(post, status, fragment):
    post.return_value = _resp(status, {"error": {"message": "server says no"}})
    with pytest.raises(AIError) as exc:
        call_ai("anthropic", "k", "m", PROMPT, 0.3, 10)
    assert fragment in exc.value.message
    assert f"HTTP {status}" in exc.value.message
    assert "server says no" in exc.value.message
    assert exc.value.hint


@pytest.mark.parametrize("error, fragment", [
    (requests.exceptions.ConnectTimeout(), "연결 시간"),
    (requests.exceptions.ReadTimeout(), "응답 대기 시간"),
    (requests.exceptions.ConnectionError(), "네트워크 오류"),
])
@patch("gitgen.ai_client.requests.post")
def test_network_errors(post, error, fragment):
    post.side_effect = error
    with pytest.raises(AIError, match=fragment):
        call_ai("anthropic", "k", "m", PROMPT, 0.3, 10)
    assert post.call_count == 1  # 자동 재시도 없음


@patch("gitgen.ai_client.requests.post")
def test_non_json_response(post):
    post.return_value = _resp(200, None, "<html>")
    with pytest.raises(AIError, match="JSON"):
        call_ai("anthropic", "k", "m", PROMPT, 0.3, 10)


@patch("gitgen.ai_client.requests.post")
def test_refusal(post):
    post.return_value = _resp(payload={"content": [], "stop_reason": "refusal"})
    with pytest.raises(AIError, match="refusal"):
        call_ai("anthropic", "k", "m", PROMPT, 0.3, 10)


@patch("gitgen.ai_client.requests.post")
def test_empty_text(post):
    post.return_value = _resp(payload={"content": [], "stop_reason": "max_tokens"})
    with pytest.raises(AIError) as exc:
        call_ai("anthropic", "k", "m", PROMPT, 0.3, 10)
    assert "max-tokens" in exc.value.hint
