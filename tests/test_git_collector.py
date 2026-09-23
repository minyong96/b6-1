import pytest

from conftest import git
from gitgen.git_collector import (
    GitError, collect_commit_diff, collect_pr_diff, collect_status, ensure_repo_root,
    parse_branch_line, parse_status,
)


@pytest.mark.parametrize("line, expected", [
    ("## main", ("main", False)),
    ("## feature/x...origin/feature/x [ahead 2]", ("feature/x", False)),
    ("## No commits yet on main", ("main", True)),
    ("## HEAD (no branch)", ("HEAD (detached)", False)),
])
def test_parse_branch_line(line, expected):
    assert parse_branch_line(line) == expected


def test_parse_status_entries():
    out = '## dev\nM  a.py\n M b.py\n?? 새파일.txt\nR  old.py -> new.py\n?? "sp ace.txt"\n'
    status = parse_status(out)
    assert status.branch == "dev"
    assert [f.path for f in status.files] == ["a.py", "b.py", "새파일.txt", "new.py", "sp ace.txt"]
    assert len(status.untracked) == 2


def test_not_repo_root(tmp_path):
    with pytest.raises(GitError, match="루트"):
        ensure_repo_root(str(tmp_path))


def test_clean_repo_has_no_changes(repo):
    status = collect_status()
    assert status.branch == "main"
    assert not status.has_changes


def test_commit_diff_prefers_staged(repo):
    (repo / "app.py").write_text("print('staged')\n")
    git(repo, "add", "app.py")
    (repo / "other.py").write_text("x = 1\n")
    git(repo, "add", "other.py")
    (repo / "app.py").write_text("print('unstaged')\n")

    diff, fallback = collect_commit_diff()
    assert not fallback
    assert "staged" in diff.diff and "unstaged" not in diff.diff
    assert "other.py" in diff.stat


def test_commit_diff_falls_back_to_worktree(repo):
    (repo / "app.py").write_text("print('changed')\n")
    diff, fallback = collect_commit_diff()
    assert fallback
    assert "changed" in diff.diff


def test_korean_filename_not_escaped(repo):
    (repo / "한글.py").write_text("a = 1\n")
    git(repo, "add", ".")
    status = collect_status()
    assert status.files[0].path == "한글.py"
    diff, _ = collect_commit_diff()
    assert "한글.py" in diff.diff


def test_pr_diff_uses_merge_base(repo):
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "feature.py").write_text("f = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "feature")
    git(repo, "checkout", "-q", "main")
    (repo / "main_only.py").write_text("m = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "main change")
    git(repo, "checkout", "-q", "feature")

    diff, fallback = collect_pr_diff("main", collect_status())
    assert not fallback
    assert "feature.py" in diff.diff
    assert "main_only.py" not in diff.diff  # main에 나중에 추가된 변경은 섞이지 않는다


def test_pr_diff_rejects_option_like_base(repo):
    with pytest.raises(GitError):
        collect_pr_diff("--output=/tmp/x", collect_status())


def test_pr_diff_unknown_base(repo):
    with pytest.raises(GitError, match="git diff"):
        collect_pr_diff("no-such-branch", collect_status())
