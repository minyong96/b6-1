"""AI 기반 Git 커밋 메시지 / PR 초안 생성기.

사용 예:
    python main.py commit
    python main.py pr --base main -c "변경 이유"
"""

import sys

from gitgen.cli import main

if __name__ == "__main__":
    sys.exit(main())
