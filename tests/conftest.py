import os
import subprocess

import pytest


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """커밋 1개가 있는 main 브랜치 저장소를 만들고 cwd를 그곳으로 옮긴다."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "tester")
    (tmp_path / "app.py").write_text("print('hello')\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("AI_API_KEY", "AI_PROVIDER", "AI_API_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
