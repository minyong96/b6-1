"""기본값·상수 모음. 모델명 등 바뀔 수 있는 값은 이 파일 한 곳에서만 관리한다."""

from __future__ import annotations

# --- 환경변수 ---
API_KEY_ENV = "AI_API_KEY"
PROVIDER_ENV = "AI_PROVIDER"
BASE_URL_ENV = "AI_API_BASE_URL"

# --- AI provider 기본값 ---
DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODELS = {
    # 커밋/PR 요약은 비교적 단순한 작업이라 저비용 모델을 기본으로 둔다.
    "anthropic": "claude-haiku-4",
    "openai": "gpt-4o-mini",
}
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = {"commit": 400, "pr": 900}
DEFAULT_TIMEOUT = 60  # 읽기 타임아웃(초)
CONNECT_TIMEOUT = 5  # 연결 타임아웃(초)
TEMPERATURE_RANGE = {"anthropic": (0.0, 1.0), "openai": (0.0, 2.0)}
MAX_TOKENS_LIMIT = 8192

# --- 출력 형식 규칙 ---
COMMIT_TITLE_RECOMMENDED = 50
COMMIT_TITLE_MAX = 72
COMMIT_BODY_MAX_BULLETS = 3
PR_TITLE_MAX = 80
PR_SECTION_MAX_BULLETS = 5
COMMIT_TYPES = (
    "feat", "fix", "docs", "style", "refactor",
    "test", "chore", "perf", "build", "ci", "revert",
)

# --- safe-mode / 전송량 제한 ---
SAFE_MAX_FILES = 10
SAFE_MAX_LINES = 200
MAX_PROMPT_CHARS = 30_000  # safe-mode 여부와 무관하게 항상 적용

# --- 종료 코드 ---
EXIT_OK = 0  # 성공 또는 변경 사항 없음
EXIT_GIT_ERROR = 1  # Git 저장소/명령 오류
EXIT_USAGE_ERROR = 2  # 잘못된 CLI 인자 (argparse 기본값과 동일)
EXIT_CONFIG_ERROR = 3  # API Key 미설정 등 환경 설정 오류
EXIT_API_ERROR = 4  # AI API 호출/응답 오류
