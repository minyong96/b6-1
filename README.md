# AI Git 커밋/PR 초안 생성기 (gitgen)

`git status`와 `git diff`로 변경 사항을 수집하고, AI API를 **REST로 1회 호출**해
커밋 메시지와 PR 제목/본문 초안을 터미널에 출력하는 Python CLI입니다.

- AI에게는 **JSON 데이터만** 받고, 길이 제한·Why/What/How to Test 템플릿은 **코드가 검증·후처리·렌더링**합니다.
- 기본으로 켜진 **safe-mode**가 민감정보 마스킹, 민감 파일 제외, 전송량 제한을 적용합니다.
- 결과는 **초안**입니다. 자동 커밋·push·PR 생성은 하지 않으며, 사용자가 검토 후 적용합니다.

```
git status / git diff ─▶ safe-mode(마스킹·제한) ─▶ 프롬프트(system 규칙 + user 데이터)
   ─▶ AI API 1회 호출 ─▶ JSON 파싱 ─▶ 검증·후처리(길이/템플릿) ─▶ 구분선으로 출력
```

## 1. 설치

요구 사항: **Python 3.10 이상**, Git

```bash
git clone <this-repo-url>
cd <this-repo>
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

가상환경 내부 pip 로 설치 
```bash
./.venv/bin/pip install -r requirements.txt
```

## 2. 환경변수(API Key) 설정

API Key는 **환경변수로만** 읽습니다. 코드나 저장소에 키를 넣지 마세요.

macOS / Linux

```bash
export AI_API_KEY="YOUR_KEY"
export AI_PROVIDER="anthropic"     # 선택: anthropic(기본) | openai
```

Windows (PowerShell)

```powershell
$env:AI_API_KEY = "YOUR_KEY"
$env:AI_PROVIDER = "anthropic"
```

| 환경변수 | 필수 | 설명 |
|---|---|---|
| `AI_API_KEY` | ✅ | 사용할 provider의 API Key |
| `AI_PROVIDER` | | `anthropic`(기본) 또는 `openai`. `--provider`로도 지정 가능 |
| `AI_API_BASE_URL` | | 엔드포인트 URL 교체 (프록시·호환 서버용) |

> `.env` 파일을 쓰는 경우 `.gitignore`에 포함되어 있는지 반드시 확인하세요. 키를 실수로 커밋했다면 삭제가 아니라 **즉시 키를 폐기(rotate)** 해야 합니다.

## 3. 사용법

**Git 저장소의 루트 디렉토리**(`.git`이 있는 위치)에서 실행합니다.

### 커밋 메시지 생성

```bash
git add <files>                    # 커밋할 변경을 스테이징 (권장)
python main.py commit
```

- 스테이징된 변경(`git diff --cached`)을 기준으로 생성합니다.
- 스테이징된 변경이 없으면 작업 트리 변경(`git diff`)으로 대체하고 경고를 출력합니다.

### PR 제목/본문 초안 생성

```bash
git switch feature/my-work
python main.py pr --base main -c "커밋/PR 작성 시간을 줄이기 위해"
```

- `git diff main...HEAD`(merge-base부터 HEAD까지, GitHub PR의 *Files changed*와 같은 기준)를 사용합니다.
- 브랜치에 커밋된 변경이 없으면 아직 커밋하지 않은 변경(`git diff HEAD`)으로 대체합니다.
- `-c/--context`로 diff만으로는 알 수 없는 **변경 이유**를 주면 Why 섹션의 근거로 사용됩니다.

### 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--provider` | `anthropic` | `anthropic` / `openai` |
| `--model`, `-m` | anthropic: `claude-haiku-4-5`, openai: `gpt-4o-mini` | 모델 ID |
| `--temperature`, `-t` | `0.3` | 낮을수록 일관적 (anthropic 0~1, openai 0~2) |
| `--max-tokens` | commit `400`, pr `900` | 출력 토큰 상한 (1~8192) |
| `--timeout` | `60` | 응답 대기 시간(초) |
| `--safe-mode` / `--no-safe-mode` | 켜짐 | 민감정보 마스킹 + 전송 제한 |
| `--max-files` | `10` | safe-mode 전송 최대 파일 수 |
| `--max-lines` | `200` | safe-mode 전송 최대 diff 줄 수 |
| `--context`, `-c` | | 변경 이유/요구사항 |
| `--dry-run` | | AI를 호출하지 않고 전송될 프롬프트만 출력 (비용 0) |
| `--base`, `-b` (pr 전용) | `main` | 비교 기준 브랜치 |

```bash
python main.py commit --model claude-sonnet-4-6 --temperature 0.2 --max-tokens 600
python main.py commit --provider openai --model gpt-4o-mini
python main.py pr --base develop --dry-run
```

> 일부 최신 모델(예: `claude-opus-5`, `claude-sonnet-5`)은 temperature 파라미터를 받지 않습니다.
> 이런 모델을 지정하면 도구가 경고를 출력하고 temperature를 요청에서 생략합니다.

## 4. 출력 예시

로그(`[INFO]`, `[WARN]`, `[ERROR]`)는 **stderr**, 결과물은 **stdout**으로 나뉩니다.
따라서 `python main.py commit > msg.txt`처럼 결과만 파일로 저장할 수 있습니다.

### 커밋 메시지

```
$ python main.py commit
[INFO] 현재 브랜치: feature/commit-pr-generator
[INFO] Git status 수집 완료: 3개 파일 변경 감지
[INFO] Git diff 수집 완료: 128줄 (staged (git diff --cached))
[INFO] safe-mode ON: 최대 10개 파일 / 200줄 전송, 민감정보 마스킹
[INFO] AI API 요청 중... (anthropic:claude-haiku-4-5, temperature=0.3, max_tokens=400)
[INFO] AI API 호출 횟수: 1회
[INFO] 토큰 사용량: 입력 2143 / 출력 118
[DONE] 커밋 메시지 생성 완료
--- Commit Message ---
feat: Git 변경 사항 기반 커밋 메시지 자동 생성 기능 추가

- git_collector.py에서 git status/diff 결과를 수집해 AI 입력으로 전달
- formatter.py에 커밋 제목 72자 제한 등 후처리 규칙 적용
- API Key 미설정 시 안내 메시지 및 에러 처리 추가
----------------------
[INFO] 생성된 문구는 초안입니다. 내용을 검토·수정한 뒤 적용하세요.
```

### PR 제목/본문

```
$ python main.py pr --base main
[INFO] 현재 브랜치: feature/commit-pr-generator
[INFO] Git status 수집 완료: 0개 파일 변경 감지
[INFO] Git diff 수집 완료: 412줄 (main...HEAD)
[INFO] safe-mode ON: 최대 10개 파일 / 200줄 전송, 민감정보 마스킹
[INFO] diff 전송량 제한: 412줄 중 200줄 전송
[INFO] AI API 요청 중... (anthropic:claude-haiku-4-5, temperature=0.3, max_tokens=900)
[INFO] AI API 호출 횟수: 1회
[DONE] PR 초안 생성 완료
--- PR Title ---
feat: 커밋/PR 자동 생성 CLI 추가
----------------

--- PR Body ---
## Why
- 커밋 메시지와 PR 설명 작성에 드는 시간을 줄이기 위함
- Git 변경 사항 기반으로 일관된 형식의 요약을 생성해 리뷰 효율 향상

## What
- git status, git diff 결과를 수집해 AI 입력 컨텍스트로 전달하는 git_collector 모듈 추가
- 커밋 메시지 생성(python main.py commit) 및 PR 초안 생성(python main.py pr) 명령 구현
- safe-mode(민감정보 마스킹, 10파일/200줄 전송 제한) 적용

## How to Test
- export AI_API_KEY="YOUR_KEY" 후 python main.py commit 실행
- python main.py pr --base main 실행 후 Why/What/How to Test 구조 확인
- pytest -q 로 단위 테스트 실행
---------------
```

### 오류 / 예외 상황

```
$ python main.py commit                      # API Key 미설정
[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다.
## 예) export AI_API_KEY="YOUR_KEY"

$ python main.py commit                      # 변경 사항 없음 (API 호출 안 함, 종료 코드 0)
[INFO] 변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다.

$ AI_API_KEY=wrong python main.py commit     # 인증 실패
[INFO] AI API 호출 횟수: 1회
[ERROR] 인증에 실패했습니다 (HTTP 401): invalid x-api-key
        → AI_API_KEY 값이 올바른지, provider(--provider)와 맞는 키인지 확인하세요.
```

| 종료 코드 | 의미 |
|---|---|
| 0 | 성공, 또는 변경 사항 없음 |
| 1 | Git 오류 (루트 디렉토리 아님, 잘못된 base 등) |
| 2 | 잘못된 CLI 인자 |
| 3 | 환경 설정 오류 (API Key 미설정) |
| 4 | AI API 호출/응답 오류 (네트워크, 401, 429, 5xx, 응답 파싱 실패 등) |

## 5. 출력 형식 규칙 (검증·후처리)

AI 출력은 확률적이므로 프롬프트 규칙만으로는 항상 지켜지지 않습니다.
이 도구는 **재생성(추가 호출) 대신 후처리**로 규칙을 보장합니다.

| 대상 | 규칙 | 처리 |
|---|---|---|
| 커밋 제목 | 1줄, 50자 권장 / 최대 72자 | 첫 줄만 사용, 따옴표·마침표 제거, 72자 초과 시 단어 경계에서 절단 + 경고, 50자 초과 시 경고 |
| 커밋 제목 | `type: 요약` (feat, fix, docs …) | 없으면 경고만 (의미 왜곡 방지를 위해 강제 수정 안 함) |
| 커밋 본문 | 불릿 1~3개 | 불릿 기호 정리, 최대 3개 |
| PR 제목 | 1줄, 최대 80자 | 80자 초과 시 절단 + 경고 |
| PR 본문 | `## Why` / `## What` / `## How to Test` + 각 불릿 ≥ 1 | 헤더는 코드가 렌더링, 빈 섹션엔 "(직접 작성 필요)" 불릿 삽입, 렌더링 후 재검증 |

> 글자 수는 Python `len()` 기준(한글 1자 = 1)입니다. 50/72자 관례는 영어 기준 터미널 폭에서 나온 것이라,
> 한글 제목은 화면에서 약 2배 폭을 차지한다는 점을 참고하세요.

## 6. 민감정보 대응 (safe-mode)

`git diff`에는 API Key, 비밀번호, 개인정보가 섞일 수 있습니다. safe-mode는 **기본으로 켜져** 있습니다.

| 단계 | 정책 |
|---|---|
| 민감 파일 제외 | `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `id_rsa*`, `credentials*`, `*secret*`, `*.tfstate` 등은 내용을 통째로 제외하고 파일명만 전달 |
| (A) 마스킹 | Anthropic/OpenAI 키, GitHub 토큰, AWS Access Key, Google API Key, Slack 토큰, JWT, Bearer 토큰, private key 블록, `password=`·`api_key:` 형태의 할당값, 이메일, 주민등록번호, 휴대폰 번호 → `***MASKED***` |
| (B) 전송 제한 | 최대 **10개 파일**, **200줄** (`--max-files`, `--max-lines`로 조정). 생략된 부분은 `--stat` 요약으로 전체 규모만 전달 |
| 항상 적용 | safe-mode와 무관하게 diff 최대 **30,000자** |
| 로그 | 마스킹 결과는 "email 1건"처럼 **종류와 건수만** 표시 (원문을 로그에 남기지 않음) |

```bash
python main.py commit --dry-run                  # 실제 전송될 프롬프트 확인 (API 호출 0회)
python main.py commit --dry-run --no-safe-mode   # 원문과 비교
```

**한계**: 정규식은 알려지지 않은 형식의 비밀(사내 토큰, 평범한 문자열 형태의 비밀번호)을 놓칠 수 있고,
테스트용 더미 이메일 등을 과하게 가릴 수도 있습니다. 민감 파일은 애초에 `.gitignore`로 커밋하지 않고,
중요한 저장소에서는 `--dry-run`으로 전송 내용을 먼저 확인하세요. `--no-safe-mode`는 원문이 외부 API로 전송되므로 경고가 출력됩니다.

## 7. 비용 / 요청 횟수

- `commit`, `pr` 명령은 각각 **AI API를 정확히 1회** 호출하며, 로그에 `AI API 호출 횟수: 1회`를 출력합니다.
- **자동 재시도는 하지 않습니다.** 401·400은 재시도해도 결과가 같고, 429에서 즉시 재시도하면 한도 문제를 악화시키기 때문입니다. 오류 원인과 대응 방법을 보고 사용자가 판단해 재실행하세요.
- 변경 사항이 없거나 `--dry-run`이면 API를 호출하지 않습니다.
- 입력 비용은 대부분 diff 크기가 결정합니다 → safe-mode 전송 제한과 30,000자 상한으로 통제합니다.
- 출력 비용은 `--max-tokens`로 상한을 둡니다. 너무 작으면 JSON이 잘려 파싱에 실패하므로, 그때는 경고에 따라 값을 늘리세요.
- 기본 모델은 저비용 모델입니다. 변경 규모가 크거나 요약 품질이 부족하면 `--model`로 상위 모델을 지정하세요.
- 큰 변경 하나보다 **작은 단위로 나눠 커밋**하는 것이 요약 품질과 비용 모두에 유리합니다.

## 8. 파라미터가 결과에 주는 영향

- **temperature**: 낮을수록(0~0.3) 같은 입력에 비슷한 결과, 높을수록(0.8+) 표현이 다양해지지만 형식 이탈·환각 위험이 커집니다. 커밋/PR은 사실 요약이므로 기본 0.3입니다.
- **max_tokens**: 출력 토큰의 **상한**이지 목표 길이가 아닙니다. 크게 잡아도 품질이 좋아지지 않고, 작으면 응답이 잘립니다. PR은 섹션이 3개라 커밋보다 크게 잡았습니다.
- **model**: 큰 모델은 긴 diff의 맥락 파악과 형식 준수가 더 좋지만 비용·지연이 큽니다.

## 9. 프로젝트 구조

```
main.py                  # 진입점
gitgen/
  cli.py                 # argparse, 전체 흐름, 종료 코드
  config.py              # 기본값·상수 (모델명, 길이 규칙, safe-mode 한도)
  git_collector.py       # git status / git diff 수집 (subprocess, shell=False)
  safe_mode.py           # 마스킹, 민감 파일 제외, 전송량 제한
  prompts.py             # system(규칙) / user(데이터) 프롬프트 구성
  ai_client.py           # REST 호출, provider 어댑터(anthropic/openai), 예외 처리
  formatter.py           # JSON 파싱, 검증·후처리, 렌더링
  log.py                 # stderr 로그
tests/                   # pytest (Git은 임시 저장소, AI API는 mock)
```

## 10. 테스트

```bash
pip install -r requirements-dev.txt
pytest -q
```

테스트는 실제 AI API를 호출하지 않습니다. `requests.post`를 mock하고, Git은 임시 저장소를 만들어 검증합니다.

## 11. 주의사항

- 생성된 커밋/PR 문구는 **최종 정답이 아닙니다.** diff에 없는 내용이 섞이지 않았는지 검토한 뒤 적용하세요.
- 이 도구는 `git status`, `git diff`만 실행합니다. `git commit`, `git push`, GitHub PR 생성은 하지 않습니다.
- 추적되지 않은(새로 만들고 `git add`하지 않은) 파일은 파일명만 전달됩니다. `git add` 후 실행하면 더 정확합니다.
- diff 안의 주석·문서에 "이전 지시를 무시하라" 같은 문장이 있어도 따르지 않도록 프롬프트에서 데이터와 지시를 분리했지만, 완벽한 방어는 아니므로 결과 검토가 필요합니다.
# b6-1