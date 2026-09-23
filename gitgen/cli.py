"""CLI 진입점: Git 수집 → safe-mode → 프롬프트 → AI API 1회 호출 → 검증·후처리 → 출력."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__, config, log
from .ai_client import PROVIDERS, AIError, AnthropicProvider, ConfigError, call_ai, get_api_key
from .formatter import (
    FormatError, format_commit, format_pr, parse_json_response, section,
    validate_commit, validate_pr,
)
from .git_collector import (
    DiffResult, GitError, GitStatus, collect_commit_diff, collect_pr_diff,
    collect_status, ensure_repo_root,
)
from .prompts import Prompt, build_commit_prompt, build_pr_prompt
from .safe_mode import apply_safe_mode, format_mask_counts, mask_text

DRAFT_NOTICE = "생성된 문구는 초안입니다. 내용을 검토·수정한 뒤 적용하세요."


# ---------------------------------------------------------------- argparse

def _positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"정수가 아닙니다: {value}")
    if n <= 0:
        raise argparse.ArgumentTypeError(f"1 이상이어야 합니다: {value}")
    return n


def _max_tokens(value: str) -> int:
    n = _positive_int(value)
    if n > config.MAX_TOKENS_LIMIT:
        raise argparse.ArgumentTypeError(f"{config.MAX_TOKENS_LIMIT} 이하여야 합니다: {value}")
    return n


def _float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"숫자가 아닙니다: {value}")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    api = common.add_argument_group("AI API 옵션")
    api.add_argument("--provider", choices=sorted(PROVIDERS),
                     default=os.environ.get(config.PROVIDER_ENV) or config.DEFAULT_PROVIDER,
                     help=f"AI provider (기본: ${config.PROVIDER_ENV} 또는 {config.DEFAULT_PROVIDER})")
    api.add_argument("--model", "-m",
                     help="모델 ID (기본: " + ", ".join(f"{k}={v}" for k, v in config.DEFAULT_MODELS.items()) + ")")
    api.add_argument("--temperature", "-t", type=_float, default=config.DEFAULT_TEMPERATURE,
                     help=f"샘플링 온도. 낮을수록 일관적 (기본: {config.DEFAULT_TEMPERATURE})")
    api.add_argument("--max-tokens", type=_max_tokens,
                     help="출력 토큰 상한 (기본: commit={commit}, pr={pr})".format(**config.DEFAULT_MAX_TOKENS))
    api.add_argument("--timeout", type=_positive_int, default=config.DEFAULT_TIMEOUT,
                     help=f"응답 대기 시간(초) (기본: {config.DEFAULT_TIMEOUT})")

    safe = common.add_argument_group("safe-mode / 전송 제한")
    safe.add_argument("--safe-mode", dest="safe_mode", action="store_true", default=True,
                      help="민감정보 마스킹 + 전송량 제한 + 민감 파일 제외 (기본: 켜짐)")
    safe.add_argument("--no-safe-mode", dest="safe_mode", action="store_false",
                      help="safe-mode 끄기 (diff 원문 전송, 최대 문자 수 제한만 적용)")
    safe.add_argument("--max-files", type=_positive_int, default=config.SAFE_MAX_FILES,
                      help=f"safe-mode 전송 최대 파일 수 (기본: {config.SAFE_MAX_FILES})")
    safe.add_argument("--max-lines", type=_positive_int, default=config.SAFE_MAX_LINES,
                      help=f"safe-mode 전송 최대 diff 줄 수 (기본: {config.SAFE_MAX_LINES})")

    etc = common.add_argument_group("기타")
    etc.add_argument("--context", "-c", help="diff만으로 알 수 없는 변경 이유/요구사항 (Why 작성에 활용)")
    etc.add_argument("--dry-run", action="store_true",
                     help="AI API를 호출하지 않고 전송될 프롬프트만 출력 (비용 0)")

    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="git status/diff를 기반으로 AI가 커밋 메시지와 PR 초안을 생성합니다.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{commit,pr}")
    sub.required = True
    sub.add_parser("commit", parents=[common], help="커밋 메시지 생성",
                   description="스테이징된 변경(없으면 작업 트리 변경)으로 커밋 메시지를 생성합니다.")
    pr = sub.add_parser("pr", parents=[common], help="PR 제목/본문 초안 생성",
                        description="base...HEAD 변경으로 PR 제목과 Why/What/How to Test 본문을 생성합니다.")
    pr.add_argument("--base", "-b", default="main", help="비교 기준 브랜치 (기본: main)")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    low, high = config.TEMPERATURE_RANGE[args.provider]
    if not low <= args.temperature <= high:
        parser.error(f"--temperature는 {args.provider}에서 {low}~{high} 범위여야 합니다: {args.temperature}")
    args.model = args.model or config.DEFAULT_MODELS[args.provider]
    args.max_tokens = args.max_tokens or config.DEFAULT_MAX_TOKENS[args.command]


# ---------------------------------------------------------------- 공통 흐름

def _log_status(status: GitStatus) -> None:
    log.info(f"현재 브랜치: {status.branch}")
    log.info(f"Git status 수집 완료: {len(status.files)}개 파일 변경 감지")
    if status.untracked:
        log.warn(f"추적되지 않은 파일 {len(status.untracked)}개는 내용 없이 파일명만 전달됩니다. "
                 "`git add` 후 실행하면 더 정확합니다.")


def _prepare_payload(
    args: argparse.Namespace, status: GitStatus, diff: DiffResult
) -> tuple[list[str], str, str, str | None]:
    """safe-mode 적용 후 (파일 목록, stat, diff, context)를 반환한다."""
    result = apply_safe_mode(diff.diff, args.safe_mode, args.max_files, args.max_lines)
    stat, context = diff.stat, args.context
    if args.safe_mode:
        counts = result.mask_counts
        stat = mask_text(stat, counts)
        context = mask_text(context, counts) if context else context
        log.info(f"safe-mode ON: 최대 {args.max_files}개 파일 / {args.max_lines}줄 전송, 민감정보 마스킹")
        if counts:
            log.info(f"민감정보 마스킹: {format_mask_counts(counts)}")
        if result.excluded_files:
            log.info(f"민감 파일 내용 제외: {', '.join(result.excluded_files)}")
        if result.line_truncated:
            log.info(f"diff 전송량 제한: {result.original_lines}줄 중 {result.sent_lines}줄 전송")
    else:
        log.warn("safe-mode OFF: diff 원문이 마스킹 없이 AI API로 전송됩니다. 민감정보 포함 여부를 확인하세요.")
    if result.char_truncated:
        log.warn(f"diff가 최대 {config.MAX_PROMPT_CHARS:,}자를 넘어 이후 내용을 생략했습니다.")
    files = [f.describe() for f in status.files]
    return files, stat, result.text, context


def _dry_run(prompt: Prompt, args: argparse.Namespace) -> int:
    print(section("System Prompt", prompt.system))
    print()
    print(section("User Prompt", prompt.user))
    log.info(f"프롬프트 길이: {prompt.total_chars:,}자 / 모델: {args.provider}:{args.model}, "
             f"temperature={args.temperature}, max_tokens={args.max_tokens}")
    log.info("--dry-run: AI API를 호출하지 않았습니다 (AI API 호출 횟수: 0회)")
    return config.EXIT_OK


def _request(args: argparse.Namespace, api_key: str, prompt: Prompt) -> dict:
    temperature: float | None = args.temperature
    if args.provider == "anthropic" and not AnthropicProvider.supports_temperature(args.model):
        log.warn(f"{args.model} 모델은 temperature를 지원하지 않아 해당 파라미터를 생략합니다.")
        temperature = None
    log.info(f"AI API 요청 중... ({args.provider}:{args.model}, temperature={temperature}, "
             f"max_tokens={args.max_tokens})")
    try:
        resp = call_ai(args.provider, api_key, args.model, prompt,
                       temperature, args.max_tokens, args.timeout)
    finally:
        # 성공/실패와 무관하게 요청을 보냈다면 호출 횟수를 남긴다 (재시도 없음).
        log.info("AI API 호출 횟수: 1회")
    if resp.input_tokens is not None:
        log.info(f"토큰 사용량: 입력 {resp.input_tokens} / 출력 {resp.output_tokens}")
    if resp.truncated:
        log.warn(f"출력이 max_tokens({args.max_tokens})에 도달해 잘렸을 수 있습니다. "
                 "--max-tokens 값을 늘려 보세요.")
    try:
        return parse_json_response(resp.text)
    except FormatError as exc:
        hint = ("--max-tokens 값을 늘려 다시 실행하세요." if resp.truncated
                else "다시 실행하거나 --temperature 값을 낮춰 보세요.")
        raise AIError(str(exc), hint) from exc


def _warn_all(warnings: list[str]) -> None:
    for w in warnings:
        log.warn(w)


# ---------------------------------------------------------------- 명령

def run_commit(args: argparse.Namespace) -> int:
    api_key = None if args.dry_run else get_api_key()  # fail-fast: Git 작업 전에 키 확인
    ensure_repo_root()
    status = collect_status()
    if not status.has_changes:
        log.info("변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다.")
        return config.EXIT_OK
    _log_status(status)

    diff, fallback = collect_commit_diff()
    notes = []
    if fallback and diff.diff.strip():
        log.warn("스테이징된 변경이 없어 작업 트리 변경(git diff)으로 생성합니다. "
                 "커밋할 파일을 `git add`한 뒤 실행하는 것을 권장합니다.")
        notes.append("아직 스테이징되지 않은 작업 트리 변경 기준임")
    if not diff.diff.strip():
        notes.append("diff 내용이 없고 새 파일 목록만 있음. 파일명을 근거로 요약할 것")
    log.info(f"Git diff 수집 완료: {diff.line_count}줄 ({diff.source})")

    files, stat, diff_text, context = _prepare_payload(args, status, diff)
    prompt = build_commit_prompt(files, stat, diff_text, context, notes)
    if args.dry_run:
        return _dry_run(prompt, args)

    data = _request(args, api_key, prompt)
    msg, warnings = format_commit(data)
    _warn_all(warnings + validate_commit(msg))
    log.done("커밋 메시지 생성 완료")
    print(section("Commit Message", msg.render()))
    log.info(DRAFT_NOTICE)
    return config.EXIT_OK


def run_pr(args: argparse.Namespace) -> int:
    api_key = None if args.dry_run else get_api_key()
    ensure_repo_root()
    status = collect_status()
    diff, fallback = collect_pr_diff(args.base, status)
    if not status.has_changes and not diff.diff.strip():
        log.info(f"변경 사항이 없습니다 ({args.base} 대비 커밋된 변경 및 작업 트리 변경 없음). "
                 "PR 초안을 생성하지 않고 종료합니다.")
        return config.EXIT_OK
    _log_status(status)
    if status.branch == args.base:
        log.warn(f"현재 브랜치가 base({args.base})와 같습니다. 작업 브랜치에서 실행하는 것을 권장합니다.")
    notes = [] if not fallback else ["브랜치에 커밋된 변경이 없어 아직 커밋하지 않은 변경 기준임"]
    if fallback:
        log.warn(f"{args.base}...HEAD 사이에 커밋된 변경이 없어 {diff.source} 기준으로 생성합니다.")
    log.info(f"Git diff 수집 완료: {diff.line_count}줄 ({diff.source})")

    files, stat, diff_text, context = _prepare_payload(args, status, diff)
    prompt = build_pr_prompt(status.branch, args.base, files, stat, diff_text, context, notes)
    if args.dry_run:
        return _dry_run(prompt, args)

    data = _request(args, api_key, prompt)
    pr, warnings = format_pr(data)
    _warn_all(warnings + validate_pr(pr))
    log.done("PR 초안 생성 완료")
    print(section("PR Title", pr.title))
    print()
    print(section("PR Body", pr.render_body()))
    log.info(DRAFT_NOTICE)
    return config.EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    handler = run_commit if args.command == "commit" else run_pr
    try:
        return handler(args)
    except ConfigError as exc:
        log.error(str(exc))
        print(f'## 예) export {config.API_KEY_ENV}="YOUR_KEY"', file=sys.stderr)
        return config.EXIT_CONFIG_ERROR
    except GitError as exc:
        log.error(str(exc))
        return config.EXIT_GIT_ERROR
    except (AIError, FormatError) as exc:
        log.error(str(exc))
        hint = getattr(exc, "hint", None)
        if hint:
            print(f"        → {hint}", file=sys.stderr)
        return config.EXIT_API_ERROR
    except KeyboardInterrupt:
        log.error("사용자에 의해 중단되었습니다.")
        return 130
