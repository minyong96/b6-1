-- =====================================================================
-- 01_schema.sql — 피트니스 센터 수업 예약 DB 스키마
-- DB: PostgreSQL 16
-- 실행 순서: 부모 테이블(member, trainer) → fitness_class → reservation
-- =====================================================================

-- 재실행할 수 있도록 기존 테이블을 자식 → 부모 순서로 삭제
DROP TABLE IF EXISTS reservation;
DROP TABLE IF EXISTS fitness_class;
DROP TABLE IF EXISTS trainer;
DROP TABLE IF EXISTS member;

-- ---------------------------------------------------------------------
-- 1. member: 회원
-- ---------------------------------------------------------------------
CREATE TABLE member (
    id               INTEGER GENERATED ALWAYS AS IDENTITY,  -- SQL:2003 표준 자동 증가 키
    name             VARCHAR(50)  NOT NULL,
    email            VARCHAR(100) NOT NULL,
    phone            VARCHAR(20),
    membership_level VARCHAR(10)  NOT NULL DEFAULT 'BASIC',
    joined_at        DATE         NOT NULL,

    CONSTRAINT pk_member PRIMARY KEY (id),
    CONSTRAINT uq_member_email UNIQUE (email),
    CONSTRAINT ck_member_level CHECK (membership_level IN ('BASIC', 'PREMIUM', 'VIP'))
);

-- ---------------------------------------------------------------------
-- 2. trainer: 트레이너
-- ---------------------------------------------------------------------
CREATE TABLE trainer (
    id        INTEGER GENERATED ALWAYS AS IDENTITY,
    name      VARCHAR(50) NOT NULL,
    specialty VARCHAR(30) NOT NULL,  -- 요가, 필라테스, 크로스핏 등
    hired_at  DATE        NOT NULL,

    CONSTRAINT pk_trainer PRIMARY KEY (id)
);

-- ---------------------------------------------------------------------
-- 3. fitness_class: 특정 일시에 열리는 1회 수업
--    trainer 1 : N fitness_class
-- ---------------------------------------------------------------------
CREATE TABLE fitness_class (
    id         INTEGER GENERATED ALWAYS AS IDENTITY,
    trainer_id INTEGER      NOT NULL,
    title      VARCHAR(100) NOT NULL,
    category   VARCHAR(30)  NOT NULL,
    price      INTEGER      NOT NULL,
    capacity   INTEGER      NOT NULL,
    start_at   TIMESTAMP    NOT NULL,

    CONSTRAINT pk_fitness_class PRIMARY KEY (id),
    CONSTRAINT fk_fitness_class_trainer
        FOREIGN KEY (trainer_id) REFERENCES trainer (id),
    CONSTRAINT ck_fitness_class_price CHECK (price >= 0),
    CONSTRAINT ck_fitness_class_capacity CHECK (capacity > 0)
);

-- ---------------------------------------------------------------------
-- 4. reservation: 수업 예약
--    member 1 : N reservation
--    fitness_class 1 : N reservation
-- ---------------------------------------------------------------------
CREATE TABLE reservation (
    id          INTEGER GENERATED ALWAYS AS IDENTITY,
    member_id   INTEGER     NOT NULL,
    class_id    INTEGER     NOT NULL,
    status      VARCHAR(10) NOT NULL DEFAULT 'RESERVED',
    rating      INTEGER,    -- 출석(ATTENDED)한 경우에만 1~5점
    reserved_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_reservation PRIMARY KEY (id),
    CONSTRAINT fk_reservation_member
        FOREIGN KEY (member_id) REFERENCES member (id),
    CONSTRAINT fk_reservation_class
        FOREIGN KEY (class_id) REFERENCES fitness_class (id),
    -- 같은 회원이 같은 수업을 중복 예약하지 못하게 막음
    CONSTRAINT uq_reservation_member_class UNIQUE (member_id, class_id),
    CONSTRAINT ck_reservation_status
        CHECK (status IN ('RESERVED', 'ATTENDED', 'CANCELED', 'NO_SHOW')),
    CONSTRAINT ck_reservation_rating
        CHECK (rating IS NULL OR (rating BETWEEN 1 AND 5 AND status = 'ATTENDED'))
);
