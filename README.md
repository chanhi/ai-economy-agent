# 📈 AI Macro-Economy Research Agent & RAG API Server

**글로벌 거시경제 일간/주간 브리핑 자동화 및 모바일 연동 RAG 검색 파이프라인**

매일 아침 글로벌 경제 뉴스(국내/해외)와 거시 지표, 시장 주도주를 수집하고, **9개의 특화된 AI 에이전트**가 협업하여 심층 분석 리포트를 작성하는 완전 자동화(Zero-touch) 리서치 시스템입니다. 작성된 리포트는 로컬 Vector DB(ChromaDB)에 즉시 임베딩되어 모바일 앱을 위한 **의미 기반 검색(Semantic Search)** API로 제공됩니다. 라즈베리파이와 같은 소형 서버에서도 API 한도 초과 없이 안정적으로 구동되도록 철저히 최적화되었습니다.

## ✨ 핵심 기능 (Key Features)

* **다중 에이전트 협업 (Multi-Agent System):** 9개의 특화된 에이전트가 데이터 선별, 전처리, 분석, 조판, 검수, 주간 결산, 테마 추출, 포트폴리오 설계를 나누어 수행합니다.
* **RAG 기반 심층 주간 결산 (Thematic Weekly Strategy):** 단순 시간순 요약이 아닌, **Two-Agent RAG 파이프라인**을 통해 이번 주 핵심 테마를 스스로 추출하고 Vector DB에서 관련 기사만 정밀 검색하여 월스트리트 수준의 심층 결산 리포트를 작성합니다.
* **모바일 앱 API 백엔드 (FastAPI & ngrok):** 완성된 데이터와 Vector DB 검색 기능을 모바일 앱(Android/iOS)에서 바로 호출할 수 있도록 고정 도메인 기반의 안전한 RESTful API(`/api/report/today`, `/api/search`)를 제공합니다.
* **강력한 보안 및 방어 로직 (Security & Rate Limit):**
* **API 방어:** 구글 Gemini API의 RPM/TPM 한도(429)를 우회하기 위한 Batch 임베딩 및 스마트 백오프(Auto-Retry) 적용
* **서버 보안:** 프롬프트 인젝션 방어, XSS 방어(HTML Escaping), 텍스트 길이 물리적 제한(Token Exhaustion 방어), API Key 인증 장착


* **장기 기억 및 자가 수정 (Memory & Self-Correction):** 과거 5일간의 시장 흐름을 기억해 트렌드 변곡점을 추론하고, 검수 에이전트(Agent D)가 리포트 품질을 채점하여 자가 수정(Feedback Loop)을 수행합니다.

---

## 🏗️ 시스템 아키텍처 및 워크플로우

1. **[Data Collection]** 국내/해외 경제 뉴스 및 주요 매크로 지표, 실적 데이터 수집
2. **[Daily Pipeline]** 데스크(Agent A)가 핵심 기사를 선별하고, 전처리기(Agent E)가 노이즈를 제거하면, 분석가(Agent B)가 과거 트렌드(Agent F)를 바탕으로 딥다이브 분석을 수행합니다.
3. **[Publish & Portfolio]** 편집장(Agent C)과 검수자(Agent D)가 일간 리포트를 조판하고, 설계사(Agent H)가 투자 성향별 액션 플랜을 추가합니다.
4. **[Vector DB Indexing]** 저장된 리포트는 즉시 `gemini-embedding-001` 모델을 통해 다차원 벡터로 변환되어 ChromaDB에 자동 적재(Upsert)됩니다. (Smart Skip 중복 방지 로직 적용)
5. **[Weekly RAG Pipeline]** 매주 주말, 테마 추출기(Agent I)가 이번 주 핵심 키워드를 뽑고 Vector DB를 검색하여, 전략가(Agent G)가 입체적인 테마별 주간 총결산을 집필합니다.
6. **[API Serving]** FastAPI 서버가 백그라운드에서 24시간 가동되며, 모바일 앱 클라이언트의 시황 조회 및 의미 기반 검색(Semantic Search) 요청을 처리합니다.

---

## 🧠 에이전트 역할 및 모델 티어링 (Model Tiering)

비용 효율과 처리 속도를 극대화하기 위해, 작업 복잡도에 따라 가벼운 모델(Lite)과 무거운 모델(Heavy)을 엄격히 분리(Routing)했습니다.

| 에이전트 | 역할 (Role) | 배정 모델 | 설명 및 목적 |
| --- | --- | --- | --- |
| **Agent A (데스크)** | 핵심 기사 선별 | **Lite** | 50개의 뉴스 풀에서 중복을 제거하고 파급력 높은 핵심 기사 8~10개 필터링 |
| **Agent E (전처리기)** | 노이즈 제거/번역 | **Lite** | 본문 속 광고를 걷어내고 완벽한 한국어로 정제하여 토큰 낭비 방지 |
| **Agent F (기억합성)** | 과거 기록 맥락화 | **Lite** | DB에 저장된 과거 기록을 유려한 트렌드 맥락으로 연결 |
| **Agent B (분석가)** | **일간 본문 딥다이브** | 🚀 **Heavy** | 과거 맥락을 대조하여 이면의 의미, 변곡점, 수혜 섹터를 심층 추론 |
| **Agent C (편집장)** | 일간 리포트 조판 | **Lite** | 분석된 데이터를 지정된 마크다운(Obsidian) 양식과 백링크 규격으로 구조화 |
| **Agent D (검수자)** | 품질 검수(피드백) | **Lite** | 지표 누락 및 양식 오류를 찾아내 Agent C에게 반려하는 Rule-based 검수 |
| **Agent H (설계사)** | 포트폴리오 액션 | 🚀 **Heavy** | 당일 거시 환경을 분석하여 7대 핵심 섹터별 비중 조절(확대/축소) 의견 제시 |
| **Agent I (테마추출)** | 주간 핵심 키워드 | **Lite** | 5일 치 리포트 아웃라인에서 이번 주 시장을 지배한 핵심 테마 3~4개 도출 |
| **Agent G (전략가)** | **주간 RAG 총결산** | 🚀 **Heavy** | 도출된 테마의 Vector DB 검색 결과를 엮어 거대한 서사를 가진 주간 결산 집필 |

---

## 🛠️ 기술 스택 (Tech Stack)

* **Language & Manager:** Python 3.11+, `uv` (초고속 패키지 매니저)
* **AI & Embedding:** Google Gemini API (`google-genai`), `gemini-embedding-001`
* **Database:** `ChromaDB` (Vector DB), `SQLite3` (Relational DB)
* **API Server & Network:** `FastAPI`, `Uvicorn`, `ngrok` (고정 도메인 터널링)
* **Data Collectors:** `yfinance`, `Alpha Vantage`, `feedparser`, `trafilatura` (본문 크롤링)

---

## ⚙️ 설치 및 실행 방법

### 1. 환경 설정 및 패키지 설치

```bash
# 레포지토리 클론 및 이동
git clone [repository-url]
cd economySummary

# uv를 이용한 초고속 패키지 설치 및 가상환경 구성
uv add google-genai requests feedparser trafilatura yfinance chromadb fastapi uvicorn

```

### 2. 자동화 파이프라인 및 서버 실행

```bash
# 1️⃣ 모바일 앱 연동 API 서버 백그라운드 실행 (8000번 포트)
uv run uvicorn server:app --host 0.0.0.0 --port 8000

# 2️⃣ 일간 리포트 파이프라인 실행 (실행 즉시 Vector DB 자동 적재)
uv run python main.py

# 3️⃣ 주간 총결산 파이프라인 실행 (RAG 기반, 주 1회 권장)
uv run python weekly_summary.py

```

*(💡 라즈베리파이 등 리눅스 환경에서는 위 스크립트들을 `systemd` 서비스 및 `crontab`으로 등록하여 완전 무인 자동화로 운영합니다.)*

---

## 📁 디렉토리 구조 (Hierarchical Architecture)

```text
economySummary/
│
├── config.py                 # 🔑 API 키, 상수 및 시스템 전역 설정
├── main.py                   # 🎬 일간 리포트 및 Vector 적재 오케스트레이터
├── weekly_summary.py         # 👑 RAG 기반 주간 결산 오케스트레이터
├── server.py                 # 🌐 모바일 연동 FastAPI 서버 (REST API & 보안 검증)
│
├── agents/                   # 🧠 [AI 에이전트 코어]
│   └── core.py               # 9개 에이전트 프롬프트 및 티어별 스마트 API 라우팅 모듈
│
├── storage/                  # 💾 [저장소 및 DB]
│   ├── vector_db.py          # ChromaDB 연동, 배치 임베딩 및 의미 기반 검색(RAG) 모듈
│   ├── memory.py             # SQLite 기반 장기 기억(Memory) 모듈
│   └── export.py             # 마크다운(.md) 포맷팅 및 Obsidian 폴더 저장
│
├── collectors/               # 📡 [데이터 수집부]
│   ├── news.py               # 뉴스 RSS/API 수집 및 본문 크롤링
│   └── market.py             # 매크로 지표, 실적/주도주 수집
│
├── chroma_data/              # 🗄️ Vector DB 영구 저장소 (Git 제외)
└── obsidian_notes/           # 📝 최종 마크다운 리포트 저장소 (연-월 분류)

```

---

## 🔑 환경 변수 및 설정 (`config.py` 또는 `.env`)

프로젝트 루트의 `config.py` 파일에 아래 키값들을 입력하여 사용합니다.

```python
GEMINI_API_KEY = "your_gemini_api_key_here"
NCP_CLIENT_ID = "your_naver_client_id_here"
NCP_CLIENT_SECRET = "your_naver_client_secret_here"
ALPHA_VANTAGE_API_KEY = "your_alpha_vantage_key_here"
DISCORD_WEBHOOK_URL = "your_discord_webhook_url_here"

# API Server Security
API_KEY_NAME = "X-API-Key"
SECRET_API_KEY = "your_secure_server_api_key_here"

```