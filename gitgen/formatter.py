"""AI 응답(JSON) 파싱 → 검증·후처리 → 렌더링.

LLM 출력은 확률적이라 규칙을 "대부분" 지키지만 "항상" 지키지는 않는다.
재생성(추가 API 호출) 대신 후처리로 길이·템플릿 규칙을 코드가 확정적으로 보장한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from . import config


class FormatError(Exception):
    """AI 응답을 해석할 수 없는 경우."""


_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n?|\n?\s*```\s*$")
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s+")
_TYPE_PREFIX = re.compile(r"^(?:" + "|".join(config.COMMIT_TYPES) + r")(?:\([^)]+\))?!?: \S")
_PLACEHOLDER = "(직접 작성 필요) AI가 이 섹션을 생성하지 못했습니다"


def parse_json_response(text: str) -> dict[str, Any]:
    """① 코드펜스 제거 → ② json.loads → ③ 첫 `{`~마지막 `}` 구간으로 재시도."""
    cleaned = _FENCE.sub("", text.strip()).strip()
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start:end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise FormatError("AI 응답을 JSON으로 해석할 수 없습니다.")


def clean_line(value: Any) -> str:
    """불릿 기호·따옴표·줄바꿈·끝 마침표를 정리한 한 줄 문자열."""
    if value is None:
        return ""
    s = " ".join(str(value).split())
    s = _BULLET_PREFIX.sub("", s)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'`":
        s = s[1:-1].strip()
    return s.rstrip(".。").strip()


def clean_bullets(values: Any, limit: int) -> list[str]:
    if isinstance(values, str):
        values = values.splitlines()
    if not isinstance(values, list):
        return []
    out = [clean_line(v) for v in values]
    return [v for v in out if v][:limit]


def truncate_at_word(s: str, limit: int) -> str:
    """limit자 이내로 자르되, 가능하면 단어 경계에서 자른다. (len()은 문자 수이므로 한글 1자 = 1)"""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    space = cut.rfind(" ")
    if space >= limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:-·")


@dataclass
class CommitMessage:
    title: str
    body: list[str] = field(default_factory=list)

    def render(self) -> str:
        if not self.body:
            return self.title
        return self.title + "\n\n" + "\n".join(f"- {b}" for b in self.body)


@dataclass
class PRDraft:
    title: str
    why: list[str]
    what: list[str]
    how_to_test: list[str]

    def render_body(self) -> str:
        sections = [("Why", self.why), ("What", self.what), ("How to Test", self.how_to_test)]
        return "\n\n".join(
            f"## {name}\n" + "\n".join(f"- {b}" for b in bullets) for name, bullets in sections
        )


def _first_line(value: Any) -> str:
    lines = [ln for ln in str(value or "").splitlines() if ln.strip()]
    return clean_line(lines[0]) if lines else ""


def format_commit(data: dict[str, Any]) -> tuple[CommitMessage, list[str]]:
    warnings: list[str] = []
    title = _first_line(data.get("title") or data.get("subject"))
    if not title:
        raise FormatError("AI 응답에 커밋 제목(title)이 없습니다.")
    if len(title) > config.COMMIT_TITLE_MAX:
        warnings.append(
            f"커밋 제목이 {len(title)}자로 최대 {config.COMMIT_TITLE_MAX}자를 넘어 잘랐습니다. 문장을 검토하세요."
        )
        title = truncate_at_word(title, config.COMMIT_TITLE_MAX)
    elif len(title) > config.COMMIT_TITLE_RECOMMENDED:
        warnings.append(f"커밋 제목이 {len(title)}자로 권장 길이({config.COMMIT_TITLE_RECOMMENDED}자)를 넘습니다.")
    if not _TYPE_PREFIX.match(title):
        # 모델 판단을 코드가 임의로 바꾸면 의미가 왜곡될 수 있어 강제 수정 대신 경고만 한다.
        warnings.append("커밋 제목에 type prefix(feat:, fix: 등)가 없습니다.")
    body = clean_bullets(data.get("body"), config.COMMIT_BODY_MAX_BULLETS)
    return CommitMessage(title, body), warnings


def format_pr(data: dict[str, Any]) -> tuple[PRDraft, list[str]]:
    warnings: list[str] = []
    title = _first_line(data.get("title"))
    if not title:
        raise FormatError("AI 응답에 PR 제목(title)이 없습니다.")
    if len(title) > config.PR_TITLE_MAX:
        warnings.append(f"PR 제목이 {len(title)}자로 최대 {config.PR_TITLE_MAX}자를 넘어 잘랐습니다.")
        title = truncate_at_word(title, config.PR_TITLE_MAX)

    sections: dict[str, list[str]] = {}
    for key, label in (("why", "Why"), ("what", "What"), ("how_to_test", "How to Test")):
        bullets = clean_bullets(data.get(key), config.PR_SECTION_MAX_BULLETS)
        if not bullets:
            # 섹션 헤더와 최소 1개 불릿을 항상 보장한다.
            warnings.append(f"PR 본문 {label} 섹션이 비어 있어 '직접 작성 필요' 항목을 넣었습니다.")
            bullets = [_PLACEHOLDER]
        sections[key] = bullets
    return PRDraft(title, **sections), warnings


def validate_commit(msg: CommitMessage) -> list[str]:
    problems = []
    if not msg.title or "\n" in msg.title:
        problems.append("커밋 제목은 1줄이어야 합니다.")
    if len(msg.title) > config.COMMIT_TITLE_MAX:
        problems.append(f"커밋 제목이 {config.COMMIT_TITLE_MAX}자를 초과합니다.")
    return problems


def validate_pr_body(body: str) -> list[str]:
    """렌더링된 본문을 한 번 더 자기검증한다: 섹션 헤더 3개 + 각 섹션 불릿 1개 이상."""
    problems = []
    for name in ("Why", "What", "How to Test"):
        m = re.search(rf"^## {re.escape(name)}\n((?:- .+\n?)+)", body, re.MULTILINE)
        if not m:
            problems.append(f"'## {name}' 섹션 또는 불릿이 없습니다.")
    return problems


def validate_pr(pr: PRDraft) -> list[str]:
    problems = validate_pr_body(pr.render_body())
    if not pr.title or "\n" in pr.title:
        problems.append("PR 제목은 1줄이어야 합니다.")
    if len(pr.title) > config.PR_TITLE_MAX:
        problems.append(f"PR 제목이 {config.PR_TITLE_MAX}자를 초과합니다.")
    return problems


def section(title: str, content: str) -> str:
    """사용자가 검토하기 쉽도록 구분선으로 구획을 나눈다."""
    header = f"--- {title} ---"
    return f"{header}\n{content}\n{'-' * len(header)}"
