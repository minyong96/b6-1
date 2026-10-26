-- =====================================================================
-- demo_fk_error.sql — 발표용 제약조건 시연 (제출물 3개 SQL 파일과 별개)
-- 실행: docker compose exec -T db psql -U fitness -d fitness_db < sql/demo_fk_error.sql
-- 실패하는 문장은 아무것도 바꾸지 않고, 성공하는 문장은 ROLLBACK 하므로
-- 몇 번을 실행해도 데이터가 그대로 유지된다.
-- 전제: 01_schema.sql, 02_seed.sql 직후 상태 (Q13, Q14 실행 전후 모두 동작)
-- psql은 오류가 나도 다음 문장을 계속 실행한다.
-- =====================================================================

\echo
\echo '=== 1. FK 위반: 존재하지 않는 회원(999)으로 예약 INSERT ==> 에러 예상'
INSERT INTO reservation (member_id, class_id) VALUES (999, 1);

\echo
\echo '=== 2. FK 위반: 존재하지 않는 수업(999)으로 예약 INSERT ==> 에러 예상'
INSERT INTO reservation (member_id, class_id) VALUES (1, 999);

\echo
\echo '=== 3. FK 위반: 존재하지 않는 트레이너(999)로 수업 INSERT ==> 에러 예상'
INSERT INTO fitness_class (trainer_id, title, category, price, capacity, start_at)
VALUES (999, '유령 트레이너 수업', '요가', 10000, 10, '2026-12-01 10:00:00');

\echo
\echo '=== 4. FK 위반: 예약이 있는 회원(1)을 DELETE ==> 에러 예상 (부모 삭제 차단)'
DELETE FROM member WHERE id = 1;

\echo
\echo '=== 5. FK 위반: 수업이 있는 트레이너(1)를 DELETE ==> 에러 예상'
DELETE FROM trainer WHERE id = 1;

\echo
\echo '=== 6. 해결: 존재하는 값으로 INSERT ==> 성공 (11번 회원은 예약이 없음, 마지막에 ROLLBACK)'
BEGIN;
INSERT INTO reservation (member_id, class_id) VALUES (11, 12);
SELECT id, member_id, class_id, status FROM reservation WHERE member_id = 11;
ROLLBACK;

\echo
\echo '=== 7. 해결: 자식이 없는 부모는 삭제 가능 (12번 회원은 예약이 없음, 마지막에 ROLLBACK)'
BEGIN;
DELETE FROM member WHERE id = 12;
SELECT COUNT(*) AS member_count FROM member;
ROLLBACK;

\echo
\echo '=== 참고 A. UNIQUE 위반: 이미 있는 이메일로 회원 INSERT ==> 에러 예상'
INSERT INTO member (name, email, joined_at)
VALUES ('중복이메일', 'minjun.kim@example.com', '2026-10-26');

\echo
\echo '=== 참고 B. UNIQUE 위반: 같은 회원이 같은 수업을 중복 예약 ==> 에러 예상'
INSERT INTO reservation (member_id, class_id) VALUES (1, 1);

\echo
\echo '=== 참고 C. CHECK 위반: 출석하지 않은 예약에 평점 입력 ==> 에러 예상'
INSERT INTO reservation (member_id, class_id, status, rating)
VALUES (11, 12, 'RESERVED', 5);

\echo
\echo '=== 시연 후 확인: 데이터는 그대로 (회원 12, 트레이너 10, 수업 15) ==='
SELECT (SELECT COUNT(*) FROM member)        AS members,
       (SELECT COUNT(*) FROM trainer)       AS trainers,
       (SELECT COUNT(*) FROM fitness_class) AS classes;
