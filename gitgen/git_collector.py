"""Git 변경 사항 수집. 제약사항에 따라 `git status`, `git diff`만 실행한다."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

# 한글 파일명이 \354\225... 형태로 이스케이프되는 것을 막는다.
_GIT_BASE = ["git", "-c", "core.quotepath=false"]
# 사용자 설정의 색상 코드·외부 diff 도구가 입력을 오염시키지 않도록 한다.
_DIFF_FLAGS = ["--no-color", "--no-ext-diff"]


class GitError(Exception):
    """Git 저장소가 아니거나 Git 명령이 실패한 경우."""


@dataclass
class FileChange:
    code: str  # porcelain XY 코드 (예: "M ", " M", "A ", "??")
    path: str

    @property
    def untracked(self) -> bool:
        return self.code == "??"

    def describe(self) -> str:
        return f"{self.code.strip() or '?'}\t{self.path}"


@dataclass
class GitStatus:
    branch: str
    files: list[FileChange] = field(default_factory=list)
    no_commits: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(self.files)

    @property
    def untracked(self) -> list[FileChange]:
        return [f for f in self.files if f.untracked]


@dataclass
class DiffResult:
    diff: str
    stat: str
    source: str  # 어떤 비교 기준으로 얻었는지 (로그/프롬프트용 설명)

    @property
    def line_count(self) -> int:
        return len(self.diff.splitlines())


def run_git(args: list[str], cwd: str | None = None) -> str:
    """인자를 리스트로 넘겨 셸을 거치지 않는다 (커맨드 인젝션 방지)."""
    try:
        proc = subprocess.run(
            [*_GIT_BASE, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitError("git 명령을 찾을 수 없습니다. Git이 설치되어 있는지 확인하세요.") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"종료 코드 {proc.returncode}"
        raise GitError(f"git {args[0]} 실행 실패: {detail}")
    return proc.stdout


def ensure_repo_root(cwd: str | None = None) -> None:
    """`git rev-parse` 대신 `.git` 경로 존재 여부로 루트를 확인한다 (status/diff 제약 준수).

    `.git`은 일반 저장소에선 디렉토리, worktree/submodule에선 파일이다.
    """
    root = cwd or os.getcwd()
    if not os.path.exists(os.path.join(root, ".git")):
        raise GitError(
            f"Git 저장소의 루트 디렉토리가 아닙니다: {root}\n"
            "        프로젝트 루트(.git이 있는 위치)에서 실행하세요."
        )


def _unquote(path: str) -> str:
    if len(path) >= 2 and path[0] == path[-1] == '"':
        return path[1:-1]
    return path


def parse_branch_line(line: str) -> tuple[str, bool]:
    """`## ...` 줄에서 (브랜치명, 커밋 없음 여부)를 추출한다."""
    info = line[3:].strip()
    for prefix in ("No commits yet on ", "Initial commit on "):
        if info.startswith(prefix):
            return info[len(prefix):], True
    if info.startswith("HEAD (no branch)"):
        return "HEAD (detached)", False
    # "main...origin/main [ahead 1]" → "main"
    return info.split("...")[0].split(" ")[0], False


def parse_status(output: str) -> GitStatus:
    branch, no_commits = "(unknown)", False
    files: list[FileChange] = []
    for line in output.splitlines():
        if not line:
            continue
        if line.startswith("## "):
            branch, no_commits = parse_branch_line(line)
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:  # rename: "old -> new"
            path = path.split(" -> ", 1)[1]
        files.append(FileChange(code=code, path=_unquote(path)))
    return GitStatus(branch=branch, files=files, no_commits=no_commits)


def collect_status(cwd: str | None = None) -> GitStatus:
    # -b: 첫 줄에 브랜치 정보가 포함되어 별도 Git 명령 없이 현재 브랜치를 알 수 있다.
    return parse_status(run_git(["status", "--porcelain=v1", "-b"], cwd))


def _diff(extra: list[str], cwd: str | None) -> tuple[str, str]:
    diff = run_git(["diff", *_DIFF_FLAGS, *extra], cwd)
    stat = run_git(["diff", *_DIFF_FLAGS, "--stat", *extra], cwd) if diff.strip() else ""
    return diff, stat


def collect_commit_diff(cwd: str | None = None) -> tuple[DiffResult, bool]:
    """커밋될 내용(스테이징 영역)을 우선 수집한다.

    반환값의 두 번째 요소는 작업 트리 diff로 대체했는지 여부.
    """
    diff, stat = _diff(["--cached"], cwd)
    if diff.strip():
        return DiffResult(diff, stat, "staged (git diff --cached)"), False
    diff, stat = _diff([], cwd)
    return DiffResult(diff, stat, "working tree (git diff)"), True


def collect_pr_diff(base: str, status: GitStatus, cwd: str | None = None) -> tuple[DiffResult, bool]:
    """merge-base부터 HEAD까지의 변경(`base...HEAD`)을 수집한다 (GitHub PR의 Files changed 기준).

    브랜치에 커밋된 변경이 없으면 아직 커밋하지 않은 변경(`git diff HEAD`)으로 대체한다.
    """
    if base.startswith("-"):
        raise GitError(f"잘못된 base 브랜치 이름입니다: {base}")
    if status.no_commits:
        diff, stat = _diff(["--cached"], cwd)
        return DiffResult(diff, stat, "staged (첫 커밋 전, git diff --cached)"), True
    diff, stat = _diff([f"{base}...HEAD"], cwd)
    if diff.strip():
        return DiffResult(diff, stat, f"{base}...HEAD"), False
    diff, stat = _diff(["HEAD"], cwd)
    return DiffResult(diff, stat, "uncommitted (git diff HEAD)"), True
