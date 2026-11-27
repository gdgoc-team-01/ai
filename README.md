# API 명세서

[AI API 명세서 (Notion)](https://app.notion.com/p/API-23a542d3d6628341a65a01e274a84793)

## API 엔드포인트

| POST 엔드포인트 | 요청 형식 및 필드 | 응답 |
| --- | --- | --- |
| `/ai/match/lost` | JSON · `item_name`, `description`, `last_seen_at`, `noticed_missing_at`, `location: {x, y}` | 습득 게시글 추천 목록 |
| `/ai/match/found` | multipart/form-data · `item_name`, `image`, `found_at`, `location_x`, `location_y`, 선택 필드 `description` | 분실 게시글 추천 목록 |
| `/ai/embed/lost` | JSON · `item_name`, `description` | 텍스트 임베딩과 카테고리 |
| `/ai/embed/found` | multipart/form-data · `image` 한 장 | 이미지 임베딩과 카테고리 |

두 매칭 API는 `{"matches":[{"post_id":103,"score":0.6284}]}` 형식으로 응답한다. 후보가 없으면 HTTP 200과 `{"matches":[]}`를 반환한다. 시간 형식은 KST 기준 `YYYY-MM-DDTHH:mm:00+09:00`이며 좌표는 캠퍼스 SVG 기준이다.

## 매칭 및 등록

LOST는 텍스트, FOUND는 업로드 이미지를 SigLIP2 Base 224로 임베딩하고 Gemini로 카테고리를 분류한다. 등록 응답은 768차원 `embedding`과 `category`다. 백엔드가 게시글과 임베딩을 저장한다.

매칭은 반대 유형 OPEN 게시글 중 같은 카테고리와 OTHER를 검색한다. 요청이 OTHER이면 카테고리 조건을 생략한다. 습득 시각이 마지막 확인 시각보다 이른 후보, 유효한 임베딩·시간·위치가 없는 후보는 제외한다.

- 임베딩 점수 = (코사인 유사도 + 1) / 2
- 시간 점수 = 2 ** (-max(0, 습득 시각과 분실 인지 시각의 차이[시간]) / 48)
- 거리 점수 = 2 ** (-SVG 유클리드 거리 / 200)
- PostgreSQL에서 전체 유효 후보의 가중합(임베딩 94%, 시간 3%, 거리 3%) 내림차순, 동점은 ID 오름차순으로 최대 20개를 반환한다.

## 설정 및 실행

1. `python -m pip install -r requirements.txt`로 설치한다. 최초 실행 시 모델 파일이 필요하다.
2. `.env.example`을 참고해 `DATABASE_URL`, `GEMINI_API_KEY`를 설정한다. 두 입력 모두 기본 모델 `gemini-3.6-flash`를 사용하며 프롬프트는 분리한다. 키 미설정·호출 실패 시 OTHER로 계속한다. 워커당 동시 분류 최대 4건, 타임아웃 30초, SDK 시도 최대 2회다. 업로드 이미지에는 서비스의 개인정보 마스킹 정책을 적용한 입력을 사용한다.
3. 백엔드와 배포를 조율해 기존 UNKNOWN 작성기를 중지하고 [카테고리 이행 SQL](sql/002_category_other.sql)을 적용한다. 신규·기존 posts 테이블을 모두 지원하며 기존 UNKNOWN 및 NULL을 OTHER로 바꾼다. 이미 존재하는 예전 특징 컬럼은 사용하지 않으며 삭제하려면 다른 소비자의 전환을 먼저 확인한다.
4. `python -m uvicorn app.main:app`으로 실행한다.

## 테스트

`python -m unittest discover -s tests -v`로 실행한다. pgvector가 활성화된 별도 테스트 DB 주소를 `TEST_DATABASE_URL`로 설정하면 임시 테이블에 실제 검색 SQL을 검증한다. Gemini는 기본적으로 모킹하며 `RUN_GEMINI_LIVE=1`에서만 유료 라이브 테스트를 실행한다.

# 로컬 DB 스키마

- PostgreSQL 17
- pgvector 0.8.7
- LOST와 FOUND 게시글은 `posts` 테이블에서 `post_type`으로 구분한다.
- 게시글 하나당 임베딩 하나를 `post_embeddings` 테이블에 저장한다.

## `posts`

| 필드명 | PostgreSQL 자료형 | NULL 허용 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT | X | 게시글 고유 ID (PK) |
| `post_type` | VARCHAR(5) | X | `LOST` / `FOUND` |
| `item_name` | VARCHAR(100) | X | 물품명 |
| `description` | TEXT | O | 물품 특징 |
| `category` | VARCHAR(30) | X | 정규화한 물품 카테고리, 기본값 OTHER |
| `last_seen_at` | TIMESTAMPTZ | O | LOST 게시글 필수 |
| `noticed_missing_at` | TIMESTAMPTZ | O | LOST 게시글 필수 |
| `found_at` | TIMESTAMPTZ | O | FOUND 게시글 필수 |
| `location_x` | DOUBLE PRECISION | X | SVG 지도 X좌표 |
| `location_y` | DOUBLE PRECISION | X | SVG 지도 Y좌표 |
| `image_key` | TEXT | O | S3 이미지 객체 키 |
| `status` | VARCHAR(20) | X | `OPEN` / `RESOLVED` |
| `created_at` | TIMESTAMPTZ | X | 게시글 등록 시각 |

## `post_embeddings`

| 필드명 | PostgreSQL 자료형 | NULL 허용 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT | X | 임베딩 고유 ID (PK) |
| `post_id` | BIGINT | X | 게시글 ID (FK → `posts.id`, UNIQUE) |
| `embedding` | VECTOR(768) | X | SigLIP2 Base 224 임베딩 벡터 |

### 테이블 관계

- `posts.id` ↔ `post_embeddings.post_id`: 1:1 관계
- LOST 게시글은 텍스트 임베딩, FOUND 게시글은 이미지 임베딩을 저장한다.
- `post_embeddings.post_id`의 UNIQUE 제약으로 게시글당 임베딩을 하나만 허용한다.
