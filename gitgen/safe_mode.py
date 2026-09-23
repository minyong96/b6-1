"""safe-mode: (A) 민감정보 마스킹 + (B) 전송량 제한 + 민감 파일 내용 제외.

정규식 마스킹은 모르는 형식의 비밀을 놓칠 수 있으므로(False Negative),
전송량 자체를 줄이는 제한(B)을 2차 방어선으로 함께 적용한다.
"""

from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass, field

from . import config

MASK = "***MASKED***"

# 구체적인 패턴을 먼저 적용해야 일반 패턴이 일부만 가리는 일이 없다.
MASK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{16,}")),
    ("github_token", re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer_token", re.compile(r"(?i)(?<=bearer )[A-Za-z0-9_\-\.=]{16,}")),
    # password = "...", API_KEY: ... 형태의 할당문은 값만 가린다.
    ("secret_assignment", re.compile(
        r"(?i)((?:api[_-]?key|secret|passw(?:or)?d|pwd|token|access[_-]?key|client[_-]?secret)"
        r"[\w\-]*[\"']?\s*[:=]\s*[\"']?)"
        # 환경변수 참조·타입 힌트 등 비밀이 아닌 값은 제외
        r"(?!os\.|getenv|process\.env|\$\{|None\b|null\b|true\b|false\b|str\b)"
        r"([^\s\"',;()\[\]]{6,})")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("resident_id", re.compile(r"\b\d{6}-?[1-4]\d{6}\b")),
    ("phone", re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b")),
]

# 패턴 검사 없이 내용을 통째로 제외하는 파일 (basename 기준)
SENSITIVE_FILE_PATTERNS = [
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", ".npmrc", ".pypirc", ".netrc",
    "credentials*", "*secret*", "*.tfstate", "*.tfvars",
]

_DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")


@dataclass
class SafeResult:
    text: str
    mask_counts: dict[str, int] = field(default_factory=dict)
    excluded_files: list[str] = field(default_factory=list)
    omitted_files: list[str] = field(default_factory=list)  # 파일 수 제한으로 빠진 파일
    original_lines: int = 0
    sent_lines: int = 0
    line_truncated: bool = False  # 파일/줄 수 제한으로 diff 일부를 생략했는지
    char_truncated: bool = False


def mask_text(text: str, counts: dict[str, int] | None = None) -> str:
    """민감 패턴을 MASK로 치환하고 종류별 건수를 counts에 누적한다."""
    counts = counts if counts is not None else {}
    for name, pattern in MASK_PATTERNS:
        if name == "secret_assignment":
            def _repl(m: re.Match[str]) -> str:
                if m.group(2) == MASK or MASK in m.group(2):
                    return m.group(0)
                counts[name] = counts.get(name, 0) + 1
                return m.group(1) + MASK
            text = pattern.sub(_repl, text)
            continue
        text, n = pattern.subn(MASK, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    return text


def is_sensitive_file(path: str) -> bool:
    name = posixpath.basename(path).lower()
    return any(fnmatch.fnmatch(name, p) for p in SENSITIVE_FILE_PATTERNS)


def split_diff(diff: str) -> list[tuple[str, list[str]]]:
    """diff 텍스트를 파일 단위 (경로, 줄 목록)으로 나눈다."""
    chunks: list[tuple[str, list[str]]] = []
    for line in diff.splitlines():
        m = _DIFF_HEADER.match(line)
        if m or not chunks:
            chunks.append((m.group(2) if m else "", [line]))
        else:
            chunks[-1][1].append(line)
    return chunks


def limit_chars(text: str, max_chars: int = config.MAX_PROMPT_CHARS) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n[... 최대 문자 수 제한으로 이후 내용 생략 ...]", True


def apply_safe_mode(
    diff: str,
    enabled: bool = True,
    max_files: int = config.SAFE_MAX_FILES,
    max_lines: int = config.SAFE_MAX_LINES,
) -> SafeResult:
    original_lines = len(diff.splitlines())
    if not enabled:
        text, cut = limit_chars(diff)
        return SafeResult(text=text, original_lines=original_lines,
                          sent_lines=len(text.splitlines()), char_truncated=cut)

    result = SafeResult(text="", original_lines=original_lines)
    out: list[str] = []
    files_used = 0
    used_lines = 0
    line_cut = False
    for path, lines in split_diff(diff):
        if path and is_sensitive_file(path):
            result.excluded_files.append(path)
            out.append(f"[safe-mode] 민감 파일로 판단되어 내용 제외: {path}")
            continue
        if path and files_used >= max_files:
            result.omitted_files.append(path)
            continue
        files_used += 1
        remaining = max_lines - used_lines
        if remaining <= 0:
            line_cut = True
            if path:
                result.omitted_files.append(path)
            continue
        out.extend(lines[:remaining])
        used_lines += min(len(lines), remaining)
        if len(lines) > remaining:
            line_cut = True
            out.append(f"[safe-mode] {path or '(diff)'}: 줄 수 제한으로 이후 내용 생략")

    result.line_truncated = bool(result.omitted_files) or line_cut
    if result.line_truncated:
        out.append(
            f"[safe-mode] 전송 제한(최대 {max_files}개 파일, {max_lines}줄)으로 이후 diff 생략. "
            "전체 변경 규모는 --stat 요약을 참고할 것."
        )
    text = mask_text("\n".join(out), result.mask_counts)
    result.text, result.char_truncated = limit_chars(text)
    result.sent_lines = used_lines
    return result


def format_mask_counts(counts: dict[str, int]) -> str:
    """로그용: 원문 없이 종류와 건수만 표시한다."""
    return ", ".join(f"{k} {v}건" for k, v in sorted(counts.items()))
