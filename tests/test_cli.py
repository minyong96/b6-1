import json
from unittest.mock import patch

import pytest

from conftest import git
from gitgen import config
from gitgen.ai_client import AIError, AIResponse
from gitgen.cli import main


def _ai(payload, truncated=False):
    return AIResponse(text=json.dumps(payload, ensure_ascii=False), model="m",
                      finish_reason="end_turn", truncated=truncated, input_tokens=100, output_tokens=50)


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")


def test_missing_key_fails_fast(repo, capsys):
    assert main(["commit"]) == config.EXIT_CONFIG_ERROR
    err = capsys.readouterr().err
    assert "[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다." in err
    assert 'export AI_API_KEY="YOUR_KEY"' in err


def test_not_repo_root(tmp_path, monkeypatch, key, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["commit"]) == config.EXIT_GIT_ERROR
    assert "루트" in capsys.readouterr().err


@patch("gitgen.cli.call_ai")
def test_no_changes_exits_zero_without_api_call(call_ai, repo, key, capsys):
    assert main(["commit"]) == config.EXIT_OK
    assert "변경 사항이 없습니다" in capsys.readouterr().err
    call_ai.assert_not_called()


@patch("gitgen.cli.call_ai")
def test_pr_no_changes(call_ai, repo, key, capsys):
    assert main(["pr"]) == config.EXIT_OK
    assert "변경 사항이 없습니다" in capsys.readouterr().err
    call_ai.assert_not_called()


@patch("gitgen.cli.call_ai")
def test_commit_success(call_ai, repo, key, capsys):
    (repo / "app.py").write_text("print('changed')\n")
    git(repo, "add", ".")
    call_ai.return_value = _ai({"title": "feat: 출력 문구 변경", "body": ["app.py 출력 수정"]})

    assert main(["commit", "--model", "claude-sonnet-4-6", "--temperature", "0.7", "--max-tokens", "300"]) == 0
    out, err = capsys.readouterr()
    assert out == "--- Commit Message ---\nfeat: 출력 문구 변경\n\n- app.py 출력 수정\n----------------------\n"
    assert "Git status 수집 완료: 1개 파일 변경 감지" in err
    assert "AI API 호출 횟수: 1회" in err
    assert "[DONE] 커밋 메시지 생성 완료" in err
    assert call_ai.call_count == 1
    args = call_ai.call_args.args
    assert args[0] == "anthropic" and args[1] == "test-key" and args[2] == "claude-sonnet-4-6"
    assert args[4] == 0.7 and args[5] == 300


@patch("gitgen.cli.call_ai")
def test_pr_success(call_ai, repo, key, capsys):
    git(repo, "checkout", "-q", "-b", "feature/x")
    (repo / "new.py").write_text("n = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "add new")
    call_ai.return_value = _ai({"title": "feat: new 모듈 추가", "why": ["이유"], "what": [], "how_to_test": ["pytest"]})

    assert main(["pr", "--base", "main", "-c", "리뷰 시간 단축"]) == 0
    out, err = capsys.readouterr()
    assert "--- PR Title ---\nfeat: new 모듈 추가" in out
    assert "## Why\n- 이유" in out
    assert "## What\n- (직접 작성 필요)" in out
    assert "## How to Test\n- pytest" in out
    assert "현재 브랜치: feature/x" in err
    prompt = call_ai.call_args.args[3]
    assert "new.py" in prompt.user
    assert "<context>\n리뷰 시간 단축\n</context>" in prompt.user
    assert call_ai.call_args.args[5] == config.DEFAULT_MAX_TOKENS["pr"]


def test_dry_run_masks_and_needs_no_key(repo, capsys):
    (repo / "demo.py").write_text('API_KEY = "sk-test1234567890abcdefghij"  # admin@example.com\n')
    git(repo, "add", ".")
    with patch("gitgen.cli.call_ai") as call_ai:
        assert main(["commit", "--dry-run"]) == 0
        call_ai.assert_not_called()
    out, err = capsys.readouterr()
    assert "sk-test1234567890" not in out and "admin@example.com" not in out
    assert "***MASKED***" in out
    assert "email 1건" in err
    assert "호출 횟수: 0회" in err


def test_dry_run_no_safe_mode_sends_raw(repo, capsys):
    (repo / "demo.py").write_text('API_KEY = "sk-test1234567890abcdefghij"\n')
    git(repo, "add", ".")
    assert main(["commit", "--dry-run", "--no-safe-mode"]) == 0
    out, err = capsys.readouterr()
    assert "sk-test1234567890abcdefghij" in out
    assert "safe-mode OFF" in err


@patch("gitgen.cli.call_ai")
def test_api_error_reports_cause(call_ai, repo, key, capsys):
    (repo / "app.py").write_text("x\n")
    call_ai.side_effect = AIError("인증에 실패했습니다 (HTTP 401): invalid x-api-key", "키를 확인하세요.")
    assert main(["commit"]) == config.EXIT_API_ERROR
    err = capsys.readouterr().err
    assert "[ERROR] 인증에 실패했습니다 (HTTP 401)" in err
    assert "키를 확인하세요." in err
    assert "호출 횟수: 1회" in err


@patch("gitgen.cli.call_ai")
def test_unparseable_response(call_ai, repo, key, capsys):
    (repo / "app.py").write_text("x\n")
    call_ai.return_value = AIResponse('{"title": "fe', "m", "max_tokens", True)
    assert main(["commit"]) == config.EXIT_API_ERROR
    err = capsys.readouterr().err
    assert "JSON" in err and "--max-tokens" in err


@patch("gitgen.cli.call_ai")
def test_temperature_omitted_for_models_without_sampling(call_ai, repo, key, capsys):
    (repo / "app.py").write_text("x\n")
    call_ai.return_value = _ai({"title": "fix: x"})
    assert main(["commit", "--model", "claude-opus-5"]) == 0
    assert call_ai.call_args.args[4] is None
    assert "temperature를 지원하지 않아" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["commit", "--temperature", "1.5"],
    ["commit", "--temperature", "abc"],
    ["commit", "--max-tokens", "0"],
    ["commit", "--max-tokens", "999999"],
    ["commit", "--provider", "nope"],
    [],
])
def test_invalid_args_rejected(argv):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == config.EXIT_USAGE_ERROR


def test_openai_allows_higher_temperature(repo, capsys):
    (repo / "app.py").write_text("x\n")
    assert main(["commit", "--provider", "openai", "--temperature", "1.5", "--dry-run"]) == 0
    assert "openai:gpt-4o-mini" in capsys.readouterr().err
