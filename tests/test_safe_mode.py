from gitgen.safe_mode import MASK, apply_safe_mode, is_sensitive_file, mask_text


def _file_diff(path, n_lines):
    header = [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}", "@@ -0,0 +1 @@"]
    return "\n".join(header + [f"+line {i}" for i in range(n_lines)])


def test_mask_common_secrets():
    text = "\n".join([
        'API_KEY = "sk-test1234567890abcdefghij"',
        "anthropic = sk-ant-api03-abcdefghijklmnop",
        "aws = AKIAABCDEFGHIJKLMNOP",
        "gh = ghp_abcdefghijklmnopqrstuvwxyz0123",
        "contact: admin@example.com",
        'password: "hunter2hunter2"',
        "주민번호 900101-1234567, 전화 010-1234-5678",
    ])
    counts = {}
    masked = mask_text(text, counts)
    for secret in ("sk-test1234567890", "sk-ant-api03", "AKIAABCDEFGHIJKLMNOP", "ghp_abc",
                   "admin@example.com", "hunter2hunter2", "900101-1234567", "010-1234-5678"):
        assert secret not in masked
    assert counts["email"] == 1
    assert counts["resident_id"] == 1


def test_mask_ignores_env_references():
    text = 'api_key = os.environ["AI_API_KEY"]\ntoken: str | None = None'
    assert mask_text(text) == text


def test_sensitive_files():
    assert is_sensitive_file(".env")
    assert is_sensitive_file("config/.env.local")
    assert is_sensitive_file("certs/server.pem")
    assert not is_sensitive_file("src/app.py")


def test_sensitive_file_content_excluded():
    diff = _file_diff(".env", 2).replace("+line 0", "+SECRET=abc") + "\n" + _file_diff("a.py", 2)
    result = apply_safe_mode(diff)
    assert result.excluded_files == [".env"]
    assert "SECRET=abc" not in result.text
    assert "a.py" in result.text


def test_limits_files_and_lines():
    diff = "\n".join(_file_diff(f"f{i}.py", 30) for i in range(12))
    result = apply_safe_mode(diff, max_files=10, max_lines=200)
    assert result.sent_lines == 200
    assert result.line_truncated
    assert "f11.py" in result.omitted_files
    assert "f10.py" in result.omitted_files
    assert "전송 제한" in result.text


def test_small_diff_untouched_and_no_notice():
    diff = _file_diff("a.py", 3)
    result = apply_safe_mode(diff)
    assert result.text == diff
    assert not result.line_truncated
    assert "[safe-mode]" not in result.text


def test_safe_mode_off_keeps_raw():
    diff = _file_diff(".env", 1) + "\n+key=sk-test1234567890abcdefghij"
    result = apply_safe_mode(diff, enabled=False)
    assert "sk-test1234567890abcdefghij" in result.text
    assert MASK not in result.text


def test_char_limit_always_applied():
    diff = _file_diff("big.py", 1) + "\n+" + "x" * 40_000
    result = apply_safe_mode(diff, enabled=False)
    assert result.char_truncated
    assert len(result.text) < 31_000
