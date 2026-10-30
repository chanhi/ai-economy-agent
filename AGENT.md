# AGENT.md — economySummary 프로젝트 가이드 (v2.0)

이 문서는 AI 코딩 에이전트 및 개발자가 `economySummary` 코드베이스를 빠르게 이해하고, 아키텍처·규약·제약 사항을 준수하며 안전하게 작업할 수 있도록 작성된 기술 지침서입니다.

---

## 1. 프로젝트 개요 (Project Overview)

**economySummary**는 국내외 거시경제·증시 뉴스와 8대 실시간 시장 지표(등락률 포함)를 수집하여 **멀티 에이전트(Multi-Agent) 협업 + Hybrid RAG**로 심층 분석 리포트를 자동 발행하고, 이를 **Vector DB(ChromaDB)**에 인덱싱하여 **주간 테마별 RAG 총결산** 및 **모바일 앱 전용 REST API & AI 비서(`FastAPI`)**로 제공하는 무인 자동화(Zero-Touch) 파이프라인입니다.

* **핵심 설계 철학**: 소형 리눅스 서버(Raspberry Pi 등) 및 제한된 LLM API 할당량 환경에서도 24시간 중단 없이 구동되도록 **직렬 처리, 마이크로 배치 큐(Queue), 모델 티어링(Heavy/Lite 분리), Pydantic Structured Output, 하이브리드 결정론적 조판**을 적용합니다.
* **런타임 & 패키지 매니저**: Python 3.11+, [`uv`](https://docs.astral.sh/uv/) (`pyproject.toml`, `uv.lock`)
* **주요 기술 스택**:
  * **LLM / Embedding**: `google-genai` (Gemini Flash Heavy/Lite 폴백 라우팅 + `Pydantic` `response_schema` + `gemini-embedding-001`)
  * **Storage**: `SQLite3` (`economy_memory.db` — 기사 대기열, 정량 시황 기억, API 캐시, 실행 메트릭), `ChromaDB` (`chroma_data/` — 코사인 유사도 벡터 검색), Obsidian 호환 Markdown (`obsidian_notes/`)
  * **API Server**: `FastAPI`, `Uvicorn` (`X-API-Key` 상수 시간 검증, Sliding-Window Rate Limiter, TTL 캐시)
  * **Collectors**: Naver NCP 뉴스 검색 API, `feedparser` (CNBC·Fed·MarketWatch·Investing·FT RSS), `yfinance` (8대 지표 + 1D/5D 등락률), `Alpha Vantage` (일별 캐시 기반 실적/주도주), `trafilatura` (페이월 도메인 자동 스킵 본문 추출)

---

## 2. 디렉토리 및 모듈 구조 (Architecture & Directory Map)

```text
economySummary/
├── main.py                  # [일간 파이프라인] 큐 로드 → 8대 지표/캐시 → Agent A(투심+선별) → 타겟 크롤링 → Hybrid RAG 분석 → 하이브리드 조판/검수/포트폴리오 → 저장 & 인덱싱
├── hourly_collector.py      # [시간당 수집기] 국내외 뉴스 수집(링크 중복 제거) → Lite Structured Output 1차 필터링 → SQLite 대기열 적재
├── weekly_summary.py        # [주간 파이프라인] 최근 7일 요약 추출 → 테마 도출(Agent I) → ChromaDB RAG 검색 → 주간 총결산(Agent G) & 벡터 인덱싱
├── server.py                # [모바일 API v2.0] 일간/주간/목록/상세/매크로 시계열/시맨틱 검색 및 POST /api/ask RAG Q&A 챗봇 서버
├── migrate_to_vector.py     # [마이그레이션/테스트] 기존 일간·주간 마크다운 전체 일괄 임베딩 및 CLI 검색 테스트 도구
├── config.py                # [설정/시크릿] API 키, 경로 단일화(BASE_DIR), ECONOMY_TEST_MODE 격리 지원 (Git 제외)
├── run_agent.sh             # [자동화 스크립트] main.py 실행 후 obsidian_notes 서브 레포지토리 자동 Git Commit & Push
├── run_weekly.sh            # [자동화 스크립트] weekly_summary.py 실행 후 obsidian_notes 자동 Git Commit & Push
│
├── agents/
│   ├── core.py              # smart_gemini_call(response_schema 지원), 하이브리드 마크다운 렌더러, 11개 에이전트 함수 정의
│   └── schemas.py           # Gemini Structured Output 강제를 위한 Pydantic v2 스키마 모음
├── collectors/
│   ├── __init__.py          # 하위 호환 패키지 re-export
│   ├── news.py              # URL SHA-1 해시 고유 ID 생성, 국내/해외 RSS 수집, 도메인 스마트 스킵 본문 크롤러(fetch_article_text)
│   └── market.py            # yfinance 8대 거시 지표(1D/5D Δ%) 스냅샷 및 Alpha Vantage 실적/주도주 수집
├── storage/
│   ├── memory.py            # SQLite 스키마 자동 마이그레이션, pending_articles, daily_memory(정량 지표), market_cache, pipeline_runs 관리
│   ├── vector_db.py         # 일간/주간 마크다운 청킹, 배치 임베딩(429 자동 대기), 과거 선례 RAG 검색(search_historical_precedents)
│   └── export.py            # obsidian_notes/YYYY-MM/ 하위 마크다운 리포트 저장
├── utils/
│   ├── logger.py            # stdout + RotatingFileHandler(5MB x 5) 통합 로거
│   ├── parser.py            # safe_json_loads 및 결정론적 마크다운 계약 검증기(validate_daily_markdown)
│   └── notifier.py          # Discord 발행 완료 알림 및 파이프라인 장애 경보(send_error_alert)
│
├── obsidian_notes/          # 생성된 일간/주간 마크다운 저장소 (독립 Private Git 저장소, 루트 Git 제외)
├── chroma_data/             # ChromaDB 영구 데이터 디렉토리 (Git 제외)
├── backup/                  # 리팩토링 이전 구버전 백업 코드 (수정 및 import 금지)
├── test/                    # 단위·계약 자동화 테스트(test_suite.py) 및 수집기 수동 테스트 (Git 제외)
└── docs/                    # 초기 설계 문서(plan.md) 및 개발 히스토리(개발일지.md)
```

---

## 3. 에이전트 구성 및 모델 티어링 (`agents/core.py` & `agents/schemas.py`)

모든 LLM 호출은 `smart_gemini_call(prompt, config_params, model_tier, retries=2, response_schema=...)`를 경유합니다.

| 구분 | 함수명 | 티어 | 스키마 (`schemas.py`) | 핵심 역할 |
| :--- | :--- | :---: | :--- | :--- |
| **1차 큐레이터** | `run_hourly_filter_agent` | `lite` | `HourlyFilterSchema` | 시간당 수집 뉴스 중 핵심 인덱스(`selected_indices`) 최대 15개 선별 |
| **Agent A (데스크)** | `run_desk_agent` | `lite` | `DeskSchema` | 중복 없는 후보 ID(`selected_ids`), `today_keyword`, `market_overview`, **투심 점수(`sentiment_score` 0~100)** 산출 |
| **Agent E (전처리)** | `run_preprocessor_agent` | `lite` | 평문 텍스트 | 크롤링 본문 노이즈 제거 및 영문 전문 번역 (*350자 미만 단문 한글은 자동 스킵*) |
| **Agent F (기억합성)** | `run_memory_synthesizer_agent` | `lite` | 평문 텍스트 | 최근 5일 `daily_memory` 기록을 3~4문장 단기 트렌드로 합성 |
| **Agent B (분석가)** | `run_analyst_agent` | **`heavy`** | `AnalystSchema` | 단기 기억 + **ChromaDB 과거 유사 선례(Hybrid RAG)**를 대조해 `selection_reason`, 4단 요약, 섹터, 용어집 생성 |
| **Agent C (편집장)** | `run_editor_agent` | `lite` | `EditorSynthesisSchema` | `market_phase`, `editor_summary`, `macro_commentary`만 생성 후 Python `render_daily_markdown()`으로 무결점 조립 |
| **Agent D (검수자)** | `run_reviewer_agent` | 규칙 | `validate_daily_markdown` | 프론트매터·지표·섹션 헤더·백링크 개수를 0.01초 내 결정론적으로 즉시 검증 |
| **Agent H (설계사)** | `run_portfolio_architect_agent` | **`heavy`** | 마크다운 표 | 공격투자형/안정투자형 7대 섹터 비중(확대/유지/축소) 액션 플랜 표 생성 |
| **Agent I (테마추출)** | `run_theme_extractor_agent` | `lite` | 쉼표 구분 키워드 | 최근 7일 일간 요약에서 주간 핵심 테마 3~4개 도출 |
| **Agent G (전략가)** | `run_chief_strategist_agent` | **`heavy`** | 마크다운 | 주간 아웃라인 + ChromaDB 테마 검색 청크를 결합해 주간 총결산 집필 |
| **RAG AI 비서** | `run_rag_qa_agent` | `lite` | `RagAnswerSchema` | 모바일 `/api/ask` 질문에 대해 검색된 과거 리포트 근거 기반 답변 및 핵심 포인트 합성 |

---

## 4. 마크다운 포맷 계약 (Markdown-Parser Contract) ⚠️ 중요

`render_daily_markdown()`, `server.py`, `storage/vector_db.py`, `weekly_summary.py`는 아래 헤더·파일명 규약을 공유합니다. 임의로 헤더 이모지나 텍스트를 변경하지 마세요.

* **파일명 규칙**:
  * 일간: `YYYY-MM-DD_{키워드}_일간_종합_경제요약.md` (`"일간"` 필수)
  * 주간: `YYYY-MM-W{주차}_주간_경제_총결산.md` (`"주간"` 필수)
* **일간 필수 섹션 순서**:
  1. YAML 프론트매터 (`tags`, `date`, `market_phase`, `sentiment_score`, `sentiment_label`)
  2. `# 🏛️ Daily Macro Report: {키워드}`
  3. `> **💡 Desk's Executive Summary:** ...` 및 `> **💡 Editor's Deep Dive Summary:** ...`
  4. `## 📊 글로벌 매크로 지표 브리핑`
  5. `## 📑 심층 분석 리포트 (총 N선)` (개별 기사는 `### {번호}. {제목}`)
  6. `## 📖 오늘의 금융/경제 단어장`
  7. `## 🔗 출처 및 참고 기사`
  8. `## 🧭 일간 포트폴리오 액션 플랜 (Action Plan)` (`### ⚔️ 공격투자형`, `### 🛡️ 안정투자형`)

---

## 5. REST API 명세 (`server.py` v2.0)

모든 `/api/*` 엔드포인트는 `X-API-Key` 헤더 인증(`secrets.compare_digest`)이 필요합니다 (`GET /` 제외).

* `GET /`: 서버 구동 확인
* `GET /api/health`: ChromaDB 청크 수 및 최근 파이프라인 실행 이력(`pipeline_runs`) 조회
* `GET /api/report/today`: 최신 일간 리포트 구조화 JSON 조회 (`sentiment`, `insights`, `macro_indicators`, `news_analysis`, `terms`, `sources`, `portfolio_plan` 포함 — 기존 앱 필드 100% 하위 호환)
* `GET /api/report/weekly`: 최신 주간 결산 리포트 JSON 조회
* `GET /api/reports?report_type=all|daily|weekly&month=YYYY-MM&limit=20&offset=0`: 리포트 아카이브 목록 조회
* `GET /api/macro/history?days=30`: 최근 N일 거시 지표 수치 및 투심 점수 시계열 조회
* `GET /api/report/detail?path=...`: 상대 경로 기반 특정 리포트 상세 조회 (Path Traversal 방어 적용)
* `GET /api/search?q=...&top_k=5`: Vector DB 코사인 유사도 검색 (분당 20회 제한 + 5분 TTL 캐시)
* `POST /api/ask`: `{"question": "...", "top_k": 5}` — 근거 인용(`citations`)이 포함된 RAG Q&A 답변 생성 (분당 10회 제한 + 5분 TTL 캐시)

---

## 6. 개발, 테스트 및 운영 명령어

```bash
# 1. 단위·계약 테스트 실행 (자동으로 ECONOMY_TEST_MODE=1 및 임시 격리 DB 사용)
uv run python test/test_suite.py

# 2. 테스트용 API 키(GEMINI_API_KEY_TEST)로 격리 실행 시 환경변수 예시
ECONOMY_TEST_MODE=1 ECONOMY_DB_PATH=/tmp/test.db uv run python hourly_collector.py

# 3. 운영 파이프라인 실행
uv run python hourly_collector.py
uv run python main.py
uv run python weekly_summary.py

# 4. 모바일 연동 API 서버 실행 (systemd 등록 운영 시 동일)
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```

---

## 7. 유지보수 시 핵심 주의사항

1. **운영/테스트 API 키 분리**: 검증이나 실험으로 Gemini API를 호출할 때는 반드시 `ECONOMY_TEST_MODE=1` 환경변수를 설정해 `.env`의 `GEMINI_API_KEY_TEST`가 사용되도록 하고, 운영 DB(`economy_memory.db`), `obsidian_notes/`, `chroma_data/`를 직접 오염시키지 않도록 `ECONOMY_DB_PATH` 등 경로 오버라이드를 활용하세요.
2. **직렬 처리 원칙 유지**: API RPM/TPM 한도 보호를 위해 `main.py`의 기사 분석 루프에 무분별한 병렬 스레드/비동기 호출을 도입하지 마세요.
3. **페이월 도메인 스킵**: `collectors/news.py`의 `SKIP_BODY_DOMAINS`(`ft.com`, `marketwatch.com`, `investing.com` 등)는 본문 크롤링 지연을 막고 RSS 요약으로 즉시 폴백하기 위한 의도된 설정입니다.
4. **옵시디언 볼트 Git 분리**: `obsidian_notes/`는 독립된 Git 저장소(`run_agent.sh`, `run_weekly.sh`에서 자동 Push)이므로 루트 저장소 작업 시 내부 `.git`을 건드리지 마세요.
