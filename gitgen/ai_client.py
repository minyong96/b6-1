"""AI API REST 연동.

SDK 대신 requests로 직접 호출해 요청(헤더·바디)·응답(상태 코드·JSON)·예외 처리를 드러낸다.
provider별 차이(인증 헤더, system 위치, 응답 경로, 종료 사유 필드)는 어댑터 클래스가 흡수한다.
자동 재시도는 하지 않는다 (1회 실행당 요청 1회 제약, 401/400은 재시도해도 결과가 같음).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from . import config
from .prompts import Prompt


class AIError(Exception):
    """AI API 호출 실패. message는 원인, hint는 사용자가 취할 행동."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(Exception):
    """API Key 미설정 등 실행 전 설정 오류."""


@dataclass
class AIResponse:
    text: str
    model: str
    finish_reason: str | None
    truncated: bool  # max_tokens에 걸려 출력이 잘렸는지
    input_tokens: int | None = None
    output_tokens: int | None = None


class Provider:
    name = ""
    default_url = ""

    def url(self) -> str:
        return os.environ.get(config.BASE_URL_ENV) or self.default_url

    def headers(self, api_key: str) -> dict[str, str]:
        raise NotImplementedError

    def body(self, model: str, prompt: Prompt, temperature: float | None, max_tokens: int) -> dict[str, Any]:
        raise NotImplementedError

    def parse(self, data: dict[str, Any]) -> AIResponse:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"
    default_url = "https://api.anthropic.com/v1/messages"

    # 최신 모델 중 일부는 temperature 등 샘플링 파라미터를 받지 않는다 (보내면 400).
    _NO_SAMPLING_PREFIXES = (
        "claude-opus-5", "claude-sonnet-5", "claude-opus-4-7", "claude-opus-4-8",
        "claude-fable", "claude-mythos",
    )

    @classmethod
    def supports_temperature(cls, model: str) -> bool:
        return not model.startswith(cls._NO_SAMPLING_PREFIXES)

    def headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def body(self, model, prompt, temperature, max_tokens):
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": prompt.system,  # Anthropic은 system을 최상위 필드로 받는다.
            "messages": [{"role": "user", "content": prompt.user}],
        }
        if temperature is not None:
            body["temperature"] = temperature
        return body

    def parse(self, data):
        stop = data.get("stop_reason")
        if stop == "refusal":
            raise AIError("모델이 요청 처리를 거절했습니다 (stop_reason=refusal).",
                          "diff에 민감하거나 부적절한 내용이 없는지 확인하세요.")
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = data.get("usage") or {}
        return AIResponse(
            text=text,
            model=data.get("model", ""),
            finish_reason=stop,
            truncated=stop == "max_tokens",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )


class OpenAIProvider(Provider):
    name = "openai"
    default_url = "https://api.openai.com/v1/chat/completions"

    def headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def body(self, model, prompt, temperature, max_tokens):
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [  # OpenAI는 system을 messages 안에 넣는다.
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        if temperature is not None:
            body["temperature"] = temperature
        return body

    def parse(self, data):
        choices = data.get("choices") or []
        if not choices:
            raise AIError("응답에 choices가 없습니다.", "잠시 후 다시 실행하세요.")
        choice = choices[0]
        usage = data.get("usage") or {}
        reason = choice.get("finish_reason")
        return AIResponse(
            text=(choice.get("message") or {}).get("content") or "",
            model=data.get("model", ""),
            finish_reason=reason,
            truncated=reason == "length",
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


PROVIDERS: dict[str, Provider] = {p.name: p for p in (AnthropicProvider(), OpenAIProvider())}


def get_api_key() -> str:
    key = os.environ.get(config.API_KEY_ENV, "").strip()
    if not key:
        raise ConfigError(f"{config.API_KEY_ENV} 환경변수가 설정되지 않았습니다.")
    return key


_STATUS_HINTS = {
    400: ("잘못된 요청입니다", "--model, --max-tokens, --temperature 값을 확인하세요."),
    401: ("인증에 실패했습니다", f"{config.API_KEY_ENV} 값이 올바른지, provider(--provider)와 맞는 키인지 확인하세요."),
    403: ("권한이 없습니다", "API Key의 권한 또는 조직/결제 설정을 확인하세요."),
    404: ("엔드포인트 또는 모델을 찾을 수 없습니다", "--model 값과 AI_API_BASE_URL 설정을 확인하세요."),
    413: ("요청이 너무 큽니다", "safe-mode(--max-files, --max-lines)로 전송량을 줄이세요."),
    429: ("요청 한도 또는 크레딧을 초과했습니다", "잠시 기다린 뒤 다시 실행하거나 사용량/결제 상태를 확인하세요."),
}


def _server_message(resp: requests.Response) -> str:
    try:
        err = resp.json().get("error")
    except ValueError:
        return resp.text[:200].strip()
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err or "")


def _raise_for_status(resp: requests.Response) -> None:
    code = resp.status_code
    if 200 <= code < 300:
        return
    detail = _server_message(resp)
    if code in _STATUS_HINTS:
        what, hint = _STATUS_HINTS[code]
    elif code >= 500:
        what, hint = "AI 서버 측 오류가 발생했습니다", "잠시 후 다시 실행하세요."
    else:
        what, hint = "AI API 요청이 실패했습니다", None
    msg = f"{what} (HTTP {code})"
    if detail:
        msg += f": {detail}"
    raise AIError(msg, hint)


def call_ai(
    provider_name: str,
    api_key: str,
    model: str,
    prompt: Prompt,
    temperature: float | None,
    max_tokens: int,
    timeout: float = config.DEFAULT_TIMEOUT,
) -> AIResponse:
    provider = PROVIDERS[provider_name]
    try:
        resp = requests.post(
            provider.url(),
            headers=provider.headers(api_key),
            json=provider.body(model, prompt, temperature, max_tokens),
            # 타임아웃 미지정 시 서버 무응답에 무한 대기하므로 (연결, 읽기) 모두 지정한다.
            timeout=(config.CONNECT_TIMEOUT, timeout),
        )
    except requests.exceptions.ConnectTimeout as exc:
        raise AIError("AI 서버 연결 시간이 초과되었습니다.", "네트워크 상태를 확인하세요.") from exc
    except requests.exceptions.ReadTimeout as exc:
        raise AIError(f"AI 응답 대기 시간({timeout}초)이 초과되었습니다.",
                      "--timeout 값을 늘리거나 잠시 후 다시 실행하세요.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise AIError("AI 서버에 연결할 수 없습니다 (네트워크 오류).",
                      "인터넷 연결, 프록시, 방화벽 설정을 확인하세요.") from exc
    except requests.exceptions.RequestException as exc:
        raise AIError(f"AI API 요청 중 오류가 발생했습니다: {exc}") from exc

    _raise_for_status(resp)
    try:
        data = resp.json()
    except ValueError as exc:
        raise AIError("AI API 응답이 JSON 형식이 아닙니다.", "잠시 후 다시 실행하세요.") from exc
    result = provider.parse(data)
    if not result.text.strip():
        hint = "--max-tokens 값을 늘려 보세요." if result.truncated else "잠시 후 다시 실행하세요."
        raise AIError(f"AI 응답이 비어 있습니다 (종료 사유: {result.finish_reason}).", hint)
    return result
