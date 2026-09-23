# 📈 AI Macro-Economy Research Agent

**글로벌 거시경제 및 주식 시장 일간/주간 브리핑 자동화 파이프라인**

매일 아침 글로벌 경제 뉴스(국내/해외)와 주요 거시 지표, 시장 주도주 및 실적 일정을 수집하고, 7개의 특화된 AI 에이전트가 협업하여 심층 분석 리포트를 작성하는 완전 자동화(Zero-touch) 리서치 시스템입니다. 라즈베리파이와 같은 소형 서버에서도 API 한도 초과 없이 안정적으로 구동되도록 철저히 최적화되었습니다.

## ✨ 주요 기능 (Key Features)

* **다중 에이전트 협업 (Multi-Agent System):** 7개의 특화된 역할을 가진 에이전트가 데이터 선별, 전처리, 분석, 조판, 검수, 주간 결산을 나누어 수행합니다.
* **API 한도 우회 및 에러 방어 (Rate Limit Protection):** 구글 Gemini API의 무료 한도(429) 및 서버 과부하(503) 에러를 방어하기 위해 **Heavy 모델의 순차 처리(Sequential) 및 자동 쿨타임 백오프**를 적용했습니다. 네이버 API 및 Alpha Vantage의 숨은 동시 호출 제한도 완벽히 우회합니다.
* **장기 기억 장착 (Memory & Synthesizer):** `SQLite3`를 활용해 과거 5일간의 시장 흐름을 기억하고, 이를 바탕으로 '어제와 달라진 오늘의 트렌드 변곡점'을 입체적으로 추론합니다.
* **자가 수정 루프 (Self-Correction):** 편집장(Agent C)이 작성한 리포트를 검수자(Agent D)가 채점하고, 품질 미달 시 반려하여 스스로 다시 작성하게 만드는 피드백 루프를 갖췄습니다.
* **다중 채널 배포:** 완성된 일간/주간 마크다운(.md) 리포트를 로컬 `Obsidian` 폴더에 저장하고, 동시에 `Discord Webhook`을 통해 스마트폰으로 요약 알림을 전송합니다.

---

## 🏗️ 시스템 아키텍처 및 워크플로우

본 시스템은 LLM 토큰 비용을 최소화하고 분석 퀄리티를 극대화하기 위해 **선별적 딥다이브(Selective Deep-dive)** 아키텍처를 따릅니다.

1. **[Data Collection]** 국내(Naver, 관련도+최신순 2-Step 필터링) 20개, 해외(CNBC, WSJ, Yahoo) 30개 뉴스 및 거시 지표(yfinance), 실적/주도주(Alpha Vantage) 수집
2. **[Agent A]** 50개의 뉴스 풀 중 파급력이 가장 큰 8개의 핵심 기사와 '오늘의 테마' 선별
3. **[Agent E]** 선별된 8개 기사의 원문을 크롤링한 뒤, 광고/노이즈를 제거하고 완벽한 한국어로 번역 (병렬 전처리)
4. **[Agent F]** 최근 5일간의 DB 기록을 불러와 '현재 거시 트렌드 맥락'으로 합성
5. **[Agent B]** 정제된 본문 전문과 트렌드 맥락을 바탕으로 **순차적(Sequential) 딥다이브 분석** 수행 (서버 과부하 방지)
6. **[Agent C ↔ Agent D]** 분석된 데이터를 융합하여 일간 마크다운 리포트를 작성하고, 검수 통과 시까지 자가 수정 루프 반복
7. **[Agent G (Weekly)]** 매주 주말, 생성된 5일 치 일간 리포트를 병합하여 '주간 경제 총결산(Weekly Strategy)' 생성
8. **[Distribution]** Markdown 노트 저장, DB 기록 업데이트, Discord 알림 전송

---

## 🧠 에이전트 역할 및 모델 티어링 (Model Tiering)

무료 API 한도(RPM/RPD)를 보호하고 자원 효율을 극대화하기 위해, 작업의 복잡도에 따라 가벼운 모델(Lite)과 무거운 모델(Heavy)을 엄격히 분리하여 배정(Routing)했습니다.

| 에이전트 | 역할 (Role) | 배정 모델 (Tier) | 설명 및 목적 |
| --- | --- | --- | --- |
| **Agent A (데스크)** | 기사 선별 및 키워드 도출 | **Lite 모델** | 50개의 제목/요약만 보고 핵심 8개를 필터링하는 단순 분류 작업 |
| **Agent E (전처리기)** | 노이즈 제거 및 번역 | **Lite 모델** | 본문 속 광고를 걷어내고 한국어로 다듬어 Agent B의 토큰 낭비 방지 |
| **Agent F (기억합성)** | 과거 기록 맥락화 | **Lite 모델** | DB에 저장된 파편화된 과거 기록을 유려한 텍스트로 연결 |
| **Agent B (분석가)** | **일간 본문 딥다이브** | 🚀 **Heavy 모델** | **(Core)** 과거 맥락을 대조하여 이면의 의미와 수혜 섹터를 추론 |
| **Agent C (편집장)** | 일간 리포트 조판 | **Lite 모델** | 완성된 분석 데이터를 정해진 마크다운 양식에 맞게 구조화 |
| **Agent D (검수자)** | 품질 검수 및 피드백 | **Lite 모델** | 누락된 지표나 양식 오류를 찾아내 Agent C에게 반려하는 Rule-based 검토 |
| **Agent G (전략가)** | **주간 총결산 (Weekly)** | 🚀 **Heavy 모델** | **(Core)** 5일 치 리포트 전문을 읽고 거대한 서사와 다음 주 관전 포인트 도출 |

---

## 🛠️ 기술 스택 (Tech Stack)

* **Language:** Python 3.11+
* **Package Manager:** `uv` (초고속 파이썬 패키지 매니저)
* **LLM API:** Google Gemini API (`google-genai`)
* **Data Sources:** `yfinance`, `Alpha Vantage`, `feedparser`, Naver Search API, `trafilatura` (본문 크롤링)
* **Database:** `SQLite3` (내장 모듈)
* **Automation:** Linux `Crontab`

---

## ⚙️ 설치 및 실행 방법

### 1. 환경 설정 및 패키지 설치

```bash
# 레포지토리 클론 및 이동
git clone [repository-url]
cd economySummary

# uv를 이용한 패키지 설치 및 가상환경 구성
uv add google-genai requests feedparser trafilatura yfinance

```

### 2. 수동 실행 테스트

```bash
# 일간 리포트 파이프라인 실행
uv run main.py

# 주간 총결산 파이프라인 실행 (주 1회 권장)
uv run weekly_summary.py

```

---

## 📁 디렉토리 구조 (Hierarchical Architecture)

```text
economySummary/
│
├── config.py                 # 🔑 API 키 및 시스템 전역 상수 (Batch 크기, 재시도 횟수 등)
├── main.py                   # 🎬 일간 리포트 오케스트레이터
├── weekly_summary.py         # 👑 주간 결산 오케스트레이터
│
├── collectors/               # 📡 [수집부]
│   ├── news.py               # 네이버(관련도+최신순 필터링)/RSS 뉴스 수집 및 원문 추출
│   └── market.py             # 매크로 지표(yfinance), 실적/주도주(Alpha Vantage)
│
├── agents/                   # 🧠 [분석 및 AI 에이전트]
│   └── core.py               # 7개 에이전트 프롬프트 및 티어별 스마트 API 호출기
│
├── storage/                  # 💾 [저장 및 메모리]
│   ├── memory.py             # SQLite 기반 장기 기억(Memory) 저장 및 호출 모듈
│   └── export.py             # 파일명 정규화 및 Obsidian 마크다운 저장
│
├── utils/                    # 🛠️ [공통 유틸리티]
│   └── notifier.py           # Discord Webhook 전송 모듈
│
└── obsidian_notes/           # 최종 마크다운 리포트 저장 폴더

```

---

## 🔑 환경 변수 및 설정 (`config.py` 또는 `.env`)

프로젝트 루트의 `config.py` 파일(또는 OS 환경변수)에 아래 키값들을 입력하여 사용합니다.

```python
GEMINI_API_KEY = "your_gemini_api_key_here"
NCP_CLIENT_ID = "your_naver_client_id_here"
NCP_CLIENT_SECRET = "your_naver_client_secret_here"
ALPHA_VANTAGE_API_KEY = "your_alpha_vantage_key_here"
DISCORD_WEBHOOK_URL = "your_discord_webhook_url_here"

```

api 서버 실행
```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```