# RUN_GUIDE — 실행 결과 만들기 (직접 따라 하기)

목표: `results/` 폴더에 쿼리 15개의 실행 결과를 남기고, 발표용 시연 자료를 준비한다.
모든 명령은 프로젝트 폴더에서 실행한다.

```bash
cd /Users/lulu/rename6-1
```

---

## 0. 먼저 환경 선택

이 맥은 macOS 12(Monterey)로 보인다(Darwin 21.6). Docker Desktop 최신 버전은 최근 macOS 3개 버전만 지원하므로 **설치가 안 될 수 있다.**
`docker --version`이 되면 **방법 A**, 안 되면 **방법 B**를 쓴다. 결과물은 둘 다 같다.

```bash
docker --version        # 버전이 나오면 방법 A
```

---

## 방법 A. Docker Compose

### A-1. 설치 확인
Docker Desktop을 설치하고 실행(고래 아이콘이 떠 있는 상태)한 뒤:
```bash
docker compose version
```

### A-2. DB 띄우기
```bash
cp -n .env.example .env          # .env가 없을 때만 복사
docker compose up -d
docker compose ps                # STATUS가 healthy 가 될 때까지 10~20초 대기
```

### A-3. 스키마·데이터 자동 적재 확인
```bash
docker compose logs db | grep -E "CREATE TABLE|INSERT|ERROR"
```
- `ERROR`가 나오면 SQL 문법 문제다. 메시지를 복사해서 Claude에게 보여 주면 고칠 수 있다.
- 이 단계 이후 아래 **공통 단계 1~5**를 진행한다. 이 방법에서 psql 명령은 아래 형태를 쓴다.

```bash
# 이후 PSQL 이라고 쓴 곳에 들어갈 명령 (방법 A)
docker compose exec -T db psql -U fitness -d fitness_db
```

---

## 방법 B. Docker 없이 로컬 PostgreSQL (Homebrew)

```bash
brew install postgresql@16
brew services start postgresql@16
export PATH="/usr/local/opt/postgresql@16/bin:$PATH"     # Apple Silicon이면 /opt/homebrew/opt/postgresql@16/bin
createdb fitness_db
psql -d fitness_db -f sql/01_schema.sql
psql -d fitness_db -f sql/02_seed.sql
```
- 방법 B에서는 스키마·데이터를 직접 넣었으므로 `ERROR` 출력이 없는지 눈으로 확인한다.
- psql 명령은 아래 형태를 쓴다.

```bash
# 이후 PSQL 이라고 쓴 곳에 들어갈 명령 (방법 B)
psql -d fitness_db
```

---

## 공통 단계 (아래 `PSQL`은 위에서 고른 명령으로 바꿔 쓴다)

### 1. 결과 폴더 준비
```bash
mkdir -p results
```

### 2. 적재 확인 → `results/00_setup_check.txt`
행 수가 12 / 10 / 15 / 30인지 확인한다.
```bash
PSQL -c "SELECT 'member' AS tbl, COUNT(*) FROM member
UNION ALL SELECT 'trainer', COUNT(*) FROM trainer
UNION ALL SELECT 'fitness_class', COUNT(*) FROM fitness_class
UNION ALL SELECT 'reservation', COUNT(*) FROM reservation;" > results/00_setup_check.txt
cat results/00_setup_check.txt
```
기대값: member 12, trainer 10, fitness_class 15, reservation 30.

테이블 구조(PK/FK/제약조건)도 남겨 둔다.
```bash
PSQL -c "\d member" -c "\d trainer" -c "\d fitness_class" -c "\d reservation" > results/00_schema_describe.txt
```

### 3. FK 에러 시연 결과 → `results/01_fk_error_demo.txt`
이 스크립트는 데이터를 바꾸지 않으므로 몇 번 실행해도 된다.
```bash
PSQL -e < sql/demo_fk_error.sql > results/01_fk_error_demo.txt 2>&1
cat results/01_fk_error_demo.txt
```
- `ERROR:  insert or update on table "reservation" violates foreign key constraint "fk_reservation_member"` 같은 줄이 1~5단계, 참고 A~C에서 나와야 한다.
- 6·7단계는 에러 없이 성공해야 한다.
- 맨 끝 확인 쿼리가 `12 | 10 | 15`이면 정상이다.
- `2>&1`을 붙여야 에러 메시지도 파일에 저장된다.

### 4. 핵심 쿼리 15개 실행 → `results/02_queries_all.txt`
**이 파일은 데이터를 바꾼다(Q13 UPDATE, Q14 DELETE, Q15 인덱스 생성). 한 번만 실행한다.**
```bash
PSQL -e < sql/03_queries.sql > results/02_queries_all.txt 2>&1
```
`-e`는 실행한 SQL을 결과 위에 함께 출력한다. 쿼리 설명 주석(`-- [Qn]`)도 같이 남는다.

확인할 것:
```bash
grep -n "ERROR" results/02_queries_all.txt || echo "에러 없음"
```

기대 결과(제가 시드 데이터로 계산한 값이므로, 다르면 알려 주세요):

| 쿼리 | 기대 결과 |
|---|---|
| Q1 | VIP 회원 3명: 윤지아, 최유나, 김민준 순 (가입일 최신순) |
| Q2 | 가격 TOP 5: 리포머 40,000 → 리포머 중급 38,000 → 하체 집중 웨이트 32,000 → 웨이트 입문 30,000 → 크로스핏 바벨 28,000 |
| Q3 | 실행일 기준 최근 30일 수업 (2026-10-26 실행 시 10개). **실행하는 날짜에 따라 달라진다** |
| Q4 | 김하은, 김나래, 김민준 3명 |
| Q7 | 9·10번 트레이너가 `class_count = 0` |
| Q8 | 11·12번 회원의 `title`, `status`가 NULL |
| Q11 | 웨이트 5.00, 크로스핏 4.50, 요가 4.40, 필라테스 4.40 (스피닝·복싱은 3.5라 제외) |
| Q12 | 오태양(11), 김나래(12) |
| Q13 | `UPDATE 2` |
| Q14 | `DELETE 5`, 확인 쿼리에서 `total_count = 25`, `canceled_count = 0` |
| Q15 | `CREATE INDEX`, 그 전후 `EXPLAIN` 2개 (둘 다 Seq Scan일 수 있음) |

> Q3은 날짜가 지날수록 결과가 줄어들어, 2026-11-24 이후에 실행하면 0건이 된다. 그 경우 `defense.md`에 "날짜가 `CURRENT_DATE` 기준"이라고 설명하면 된다.

### 5. 쿼리별 개별 파일(선택)
제출 형식이 "쿼리마다 결과"를 요구하므로, 평가자가 보기 편하게 `02_queries_all.txt`를 그대로 내도 되고 캡처로 대체해도 된다.
DBeaver / TablePlus에서 `sql/03_queries.sql`을 열어 쿼리를 하나씩 실행하고 결과 창을 캡처하면 `results/q01.png` 같은 이미지로 남길 수 있다.
(이미 Q13·Q14를 실행했다면 아래 **초기화**를 먼저 한다.)

---

## 6. 초기화 (처음 상태로 되돌리기)

쿼리를 다시 실행하거나 SQL을 고친 뒤 다시 적재할 때 사용한다.

**방법 A (Docker)**
```bash
docker compose down -v
docker compose up -d
```

**방법 B (로컬)**
```bash
dropdb fitness_db && createdb fitness_db
psql -d fitness_db -f sql/01_schema.sql
psql -d fitness_db -f sql/02_seed.sql
```

---

## 7. 제출 전 최종 확인

```bash
ls -l results/
```
- [ ] `00_setup_check.txt`: 행 수 12 / 10 / 15 / 30
- [ ] `00_schema_describe.txt`: 테이블 구조
- [ ] `01_fk_error_demo.txt`: FK 에러와 해결 시연
- [ ] `02_queries_all.txt`: Q1~Q15 결과, `ERROR` 없음
- [ ] (선택) `docs/erd.png`
- [ ] 제출 SQL 3개: `sql/01_schema.sql`, `sql/02_seed.sql`, `sql/03_queries.sql` (`demo_fk_error.sql`은 발표용이라 제출 시 빼도 됨)

---

## 자주 만나는 문제

| 증상 | 원인 / 해결 |
|---|---|
| `docker: command not found` | Docker Desktop이 없거나 실행 중이 아님 → 방법 B 사용 |
| `port is already allocated` | 5432 포트 사용 중 → `.env`의 `POSTGRES_PORT=5433`으로 변경 후 다시 `up -d` |
| 스키마를 고쳤는데 반영 안 됨 | 초기화 스크립트는 최초 1회만 실행됨 → `docker compose down -v` 후 재기동 |
| `relation "member" does not exist` | 적재 실패 → `docker compose logs db`로 `ERROR` 확인 |
| Q15에서 `relation "idx_reservation_member_id" already exists` | `03_queries.sql`을 두 번 실행함 → 초기화 후 한 번만 실행 |
| `password authentication failed` | `.env`의 계정/비밀번호를 바꾼 뒤 기존 볼륨이 남아 있음 → `down -v` |
| 결과 파일이 비어 있음 | 명령 끝에 `> 파일명`을 붙였는지, DB가 healthy 상태인지 확인 |
