-- =====================================================================
-- 03_queries.sql — 피트니스 센터 수업 예약 DB 핵심 쿼리 15개
-- DB: PostgreSQL 16
-- 실행 전제: 01_schema.sql → 02_seed.sql 실행 완료
-- 주의: Q13(UPDATE), Q14(DELETE)는 데이터를 바꾸므로, 처음 상태로 되돌리려면
--       docker compose down -v && docker compose up -d 로 다시 적재한다.
-- =====================================================================


-- =====================================================================
-- 1. 기본 조회 (Q1 ~ Q4)
-- =====================================================================

-- [Q1] VIP 회원 목록을 최근 가입한 순서로 조회한다.
SELECT id, name, email, joined_at
FROM member
WHERE membership_level = 'VIP'
ORDER BY joined_at DESC;

-- [Q2] 가격이 가장 비싼 수업 TOP 5를 조회한다.
-- LIMIT: PostgreSQL 문법 (표준 SQL은 FETCH FIRST 5 ROWS ONLY)
SELECT id, title, category, price
FROM fitness_class
ORDER BY price DESC, id
LIMIT 5;

-- [Q3] 최근 30일 안에 열린(이미 시작한) 수업 목록을 조회한다.
-- CURRENT_DATE - INTERVAL '30 days': PostgreSQL 날짜 연산 문법
SELECT id, title, category, start_at
FROM fitness_class
WHERE start_at >= CURRENT_DATE - INTERVAL '30 days'
  AND start_at <  CURRENT_TIMESTAMP
ORDER BY start_at;

-- [Q4] 이름에 '김'이 들어간 회원을 검색한다.
SELECT id, name, email, membership_level
FROM member
WHERE name LIKE '%김%'
ORDER BY name;


-- =====================================================================
-- 2. 조인 (Q5 ~ Q8)
-- =====================================================================

-- [Q5] 수업마다 담당 트레이너 이름과 전문 분야를 함께 조회한다. (INNER JOIN)
SELECT fc.id, fc.title, fc.start_at, t.name AS trainer_name, t.specialty
FROM fitness_class fc
INNER JOIN trainer t ON t.id = fc.trainer_id
ORDER BY fc.start_at;

-- [Q6] 예약 내역을 회원명, 수업명, 수업 일시, 예약 상태와 함께 조회한다. (INNER JOIN 3개 테이블)
SELECT r.id AS reservation_id, m.name AS member_name, fc.title, fc.start_at, r.status
FROM reservation r
INNER JOIN member m         ON m.id  = r.member_id
INNER JOIN fitness_class fc ON fc.id = r.class_id
ORDER BY fc.start_at, m.name;

-- [Q7] 모든 트레이너의 담당 수업 수를 조회한다. 수업이 없는 트레이너도 0으로 나온다. (LEFT JOIN)
SELECT t.id, t.name, t.specialty, COUNT(fc.id) AS class_count
FROM trainer t
LEFT JOIN fitness_class fc ON fc.trainer_id = t.id
GROUP BY t.id, t.name, t.specialty
ORDER BY class_count DESC, t.id;

-- [Q8] 모든 회원과 예약한 수업을 조회한다. 예약이 없는 회원은 수업 정보가 NULL로 나온다. (LEFT JOIN)
SELECT m.id, m.name, fc.title, r.status
FROM member m
LEFT JOIN reservation r     ON r.member_id = m.id
LEFT JOIN fitness_class fc  ON fc.id = r.class_id
ORDER BY m.id, fc.start_at;


-- =====================================================================
-- 3. 집계 (Q9 ~ Q11)
-- =====================================================================

-- [Q9] 회원별 예약 횟수를 많은 순서로 집계한다. (COUNT + GROUP BY)
SELECT m.id, m.name, COUNT(*) AS reservation_count
FROM member m
INNER JOIN reservation r ON r.member_id = m.id
GROUP BY m.id, m.name
ORDER BY reservation_count DESC, m.id;

-- [Q10] 트레이너별로 실제 출석한 예약의 매출 합계를 구한다. (SUM + GROUP BY)
SELECT t.id, t.name, COUNT(*) AS attended_count, SUM(fc.price) AS total_revenue
FROM trainer t
INNER JOIN fitness_class fc ON fc.trainer_id = t.id
INNER JOIN reservation r    ON r.class_id = fc.id
WHERE r.status = 'ATTENDED'
GROUP BY t.id, t.name
ORDER BY total_revenue DESC;

-- [Q11] 카테고리별 평균 평점을 구하고, 평균 4.0 이상인 카테고리만 남긴다. (AVG + GROUP BY + HAVING)
SELECT fc.category,
       COUNT(r.rating)          AS rating_count,
       ROUND(AVG(r.rating), 2)  AS avg_rating
FROM fitness_class fc
INNER JOIN reservation r ON r.class_id = fc.id
WHERE r.rating IS NOT NULL
GROUP BY fc.category
HAVING AVG(r.rating) >= 4.0
ORDER BY avg_rating DESC;


-- =====================================================================
-- 4. 서브쿼리 (Q12)
-- =====================================================================

-- [Q12] 한 번도 예약하지 않은 회원을 찾는다. (NOT EXISTS 서브쿼리)
SELECT m.id, m.name, m.email, m.joined_at
FROM member m
WHERE NOT EXISTS (
    SELECT 1
    FROM reservation r
    WHERE r.member_id = m.id
)
ORDER BY m.id;


-- =====================================================================
-- 5. 데이터 수정 및 삭제 (Q13 ~ Q14)
-- =====================================================================

-- (확인용) 변경 전: 이미 시작한 수업인데 RESERVED로 남아 있는 예약
SELECT r.id, r.member_id, r.class_id, fc.start_at, r.status
FROM reservation r
INNER JOIN fitness_class fc ON fc.id = r.class_id
WHERE r.status = 'RESERVED'
  AND fc.start_at < CURRENT_TIMESTAMP;

-- [Q13] 이미 시작한 수업의 RESERVED 예약을 NO_SHOW(노쇼)로 변경한다. (UPDATE + 서브쿼리 조건)
UPDATE reservation
SET status = 'NO_SHOW'
WHERE status = 'RESERVED'
  AND class_id IN (
      SELECT id
      FROM fitness_class
      WHERE start_at < CURRENT_TIMESTAMP
  );

-- (확인용) 변경 후: 상태별 예약 건수
SELECT status, COUNT(*) AS cnt
FROM reservation
GROUP BY status
ORDER BY status;

-- [Q14] 취소(CANCELED)된 예약 기록을 삭제한다. (DELETE)
DELETE FROM reservation
WHERE status = 'CANCELED';

-- (확인용) 삭제 후: CANCELED 예약이 0건이고 전체 건수가 줄었는지 확인
SELECT COUNT(*) AS total_count,
       SUM(CASE WHEN status = 'CANCELED' THEN 1 ELSE 0 END) AS canceled_count
FROM reservation;


-- =====================================================================
-- 6. 인덱스 (Q15)
-- =====================================================================

-- (확인용) 인덱스 생성 전 실행 계획
-- EXPLAIN: PostgreSQL 문법 (표준 SQL 아님)
EXPLAIN
SELECT * FROM reservation WHERE class_id = 6;

-- [Q15] reservation.class_id에 인덱스를 만든다.
-- 적용 이유: 수업별 예약 조회·JOIN·집계(Q6, Q10, Q11)에서 class_id로 자주 찾는데,
--           PostgreSQL은 FK 컬럼에 인덱스를 자동으로 만들지 않고, UNIQUE (member_id, class_id)의
--           자동 인덱스는 member_id로 시작해 class_id 단독 조회에는 쓸 수 없기 때문이다.
CREATE INDEX idx_reservation_class_id ON reservation (class_id);

-- (확인용) 인덱스 생성 후 실행 계획
-- 데이터가 적으면 인덱스보다 전체 스캔(Seq Scan)이 더 싸다고 판단해 그대로 Seq Scan이 나올 수 있다.
EXPLAIN
SELECT * FROM reservation WHERE class_id = 6;
