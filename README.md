# API 명세서

[AI API 명세서 (Notion)](https://app.notion.com/p/AI-API-41c3df0b367f80b2a7d8e970e124a506)

## API 엔드포인트

| Method | Endpoint | 기능 |
| --- | --- | --- |
| POST | `/ai/match/lost` | 분실물 텍스트로 습득 게시글 검색 |
| POST | `/ai/match/found` | 습득물 이미지로 분실 게시글 검색 |
| POST | `/ai/embed/lost` | 분실 게시글 텍스트 임베딩 생성 |
| POST | `/ai/embed/found` | 습득 게시글 이미지 임베딩 생성 |

요청·응답 형식 및 오류 응답의 상세 내용은 위 Notion 명세서를 따른다.

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
