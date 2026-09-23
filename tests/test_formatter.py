import pytest

from gitgen.formatter import (
    FormatError, format_commit, format_pr, parse_json_response, truncate_at_word,
    validate_pr, validate_pr_body,
)


def test_parse_plain_json():
    assert parse_json_response('{"title": "feat: x"}') == {"title": "feat: x"}


def test_parse_code_fence():
    assert parse_json_response('```json\n{"title": "a"}\n```') == {"title": "a"}


def test_parse_with_surrounding_text():
    assert parse_json_response('결과입니다:\n{"title": "a"}\n감사합니다') == {"title": "a"}


def test_parse_broken_json():
    with pytest.raises(FormatError):
        parse_json_response('{"title": "잘린 응답')


def test_commit_cleans_and_limits():
    msg, warnings = format_commit({
        "title": '"feat: 커밋 메시지 생성 기능 추가."\n두번째 줄',
        "body": ["- a.py 수정.", "* b.py 추가", "", "c", "d"],
    })
    assert msg.title == "feat: 커밋 메시지 생성 기능 추가"
    assert msg.body == ["a.py 수정", "b.py 추가", "c"]
    assert warnings == []
    assert msg.render() == "feat: 커밋 메시지 생성 기능 추가\n\n- a.py 수정\n- b.py 추가\n- c"


def test_commit_title_truncated_to_72():
    long_title = "feat: " + "word " * 30
    msg, warnings = format_commit({"title": long_title, "body": []})
    assert len(msg.title) <= 72
    assert not msg.title.endswith(" ")
    assert any("잘랐습니다" in w for w in warnings)


def test_commit_title_over_50_warns():
    msg, warnings = format_commit({"title": "fix: " + "가" * 50})
    assert len(msg.title) == 55
    assert any("권장" in w for w in warnings)


def test_commit_missing_prefix_warns_but_keeps():
    msg, warnings = format_commit({"title": "로그인 버그 수정"})
    assert msg.title == "로그인 버그 수정"
    assert any("prefix" in w for w in warnings)


def test_commit_scope_prefix_ok():
    _, warnings = format_commit({"title": "feat(cli): 옵션 추가"})
    assert warnings == []


def test_commit_missing_title():
    with pytest.raises(FormatError):
        format_commit({"body": ["x"]})


def test_pr_fills_empty_sections():
    pr, warnings = format_pr({"title": "feat: PR", "why": [], "what": ["a"], "how_to_test": None})
    assert pr.why[0].startswith("(직접 작성 필요)")
    assert pr.how_to_test[0].startswith("(직접 작성 필요)")
    assert len(warnings) == 2
    body = pr.render_body()
    assert validate_pr_body(body) == []
    assert "## Why\n- " in body and "## What\n- a" in body and "## How to Test\n- " in body


def test_pr_title_truncated_to_80():
    pr, _ = format_pr({"title": "feat: " + "긴제목 " * 40, "why": ["a"], "what": ["b"], "how_to_test": ["c"]})
    assert len(pr.title) <= 80
    assert validate_pr(pr) == []


def test_validate_pr_body_detects_missing():
    assert validate_pr_body("## Why\n- a\n\n## What\n\n## How to Test\n- c") == [
        "'## What' 섹션 또는 불릿이 없습니다."
    ]


def test_truncate_at_word_hard_cut_without_space():
    assert truncate_at_word("가" * 100, 72) == "가" * 72
