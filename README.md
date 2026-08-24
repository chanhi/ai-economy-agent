# 📈 AI Macro-Economy Research Agent 
**글로벌 거시경제 및 주식 시장 일간 브리핑 자동화 파이프라인**

매일 아침 글로벌 경제 뉴스(국내/해외)와 주요 거시 지표를 수집하고, 6개의 특화된 AI 에이전트가 협업하여 심층 분석 리포트를 작성하는 완전 자동화(Zero-touch) 리서치 시스템입니다. 라즈베리파이와 같은 소형 서버에서도 API 한도 초과 없이 안정적으로 구동되도록 최적화되었습니다.

## ✨ 주요 기능 (Key Features)
* **다중 에이전트 협업 (Multi-Agent System):** 6개의 특화된 역할을 가진 에이전트가 데이터 선별, 전처리, 분석, 조판, 검수를 나누어 수행합니다.
* **장기 기억 장착 (Memory & Synthesizer):** `SQLite3`를 활용해 과거 5일간의 시장 흐름을 기억하고, 이를 바탕으로 '어제와 달라진 오늘의 트렌드 변곡점'을 입체적으로 추론합니다.
* **자가 수정 루프 (Self-Correction):** 편집장(Agent C)이 작성한 리포트를 검수자(Agent D)가 채점하고, 품질 미달 시 반려하여 스스로 다시 작성하게 만드는 피드백 루프를 갖췄습니다.
* **API 한도 우회 및 에러 방어:** 구글 Gemini API의 무료 한도(429) 및 서버 과부하(503) 에러를 스스로 감지하고 대기/재시도/대체 모델 스위칭을 수행합니다.
* **다중 채널 배포:** 완성된 마크다운(.md) 리포트를 로컬 `Obsidian` 폴더에 저장하고, 동시에 `Discord Webhook`을 통해 스마트폰으로 요약 알림을 전송합니다.

---

## 🏗️ 시스템 아키텍처 및 워크플로우

본 시스템은 LLM 토큰 비용을 최소화하고 분석 퀄리티를 극대화하기 위해 **선별적 딥다이브(Selective Deep-dive)** 아키텍처를 따릅니다.

1. **[Data Collection]** 국내(Naver) 20개, 해외(CNBC, WSJ, Yahoo) 30개 뉴스 및 실시간 매크로 지표(yfinance) 수집
2. **[Agent A]** 50개의 뉴스 풀 중 파급력이 가장 큰 8개의 핵심 기사와 '오늘의 테마' 선별
3. **[Agent E]** 선별된 8개 기사의 원문을 크롤링한 뒤, 광고/노이즈를 제거하고 완벽한 한국어로 번역 (전처리)
4. **[Agent F]** 최근 5일간의 DB 기록을 불러와 '현재 거시 트렌드 맥락'으로 합성
5. **[Agent B]** 정제된 본문 전문과 트렌드 맥락을 바탕으로 4개씩 병렬(Parallel) 딥다이브 분석 수행
6. **[Agent C ↔ Agent D]** 분석된 데이터를 융합하여 마크다운 리포트를 작성하고, 검수 조건 충족 시까지 자가 수정 루프 반복
7. **[Distribution]** Markdown 노트 저장, DB 기록 업데이트, Discord 알림 전송

---

## 🧠 에이전트 역할 및 모델 티어링 (Model Tiering)

무료 API 한도(RPM/RPD)를 보호하고 자원 효율을 극대화하기 위해, **작업의 복잡도에 따라 가벼운 모델(Lite)과 무거운 모델(Heavy)을 분리하여 배정(Routing)**했습니다.

| 에이전트 | 역할 (Role) | 배정 모델 (Tier) | 설명 및 목적 |
| :--- | :--- | :--- | :--- |
| **Agent A (데스크)** | 기사 선별 및 키워드 도출 | **Lite 모델** | 50개의 제목/요약만 보고 핵심 8개를 필터링하는 단순 분류 작업 |
| **Agent E (전처리기)**| 노이즈 제거 및 번역 | **Lite 모델** | 본문 속 광고를 걷어내고 한국어로 다듬어 Agent B의 토큰 낭비 방지 |
| **Agent F (기억합성)**| 과거 기록 맥락화 | **Lite 모델** | DB에 저장된 파편화된 과거 기록을 유려한 텍스트로 연결 |
| **Agent B (분석가)** | **본문 딥다이브 분석** | 🚀 **Heavy 모델** | **(Core)** 과거 맥락을 대조하여 이면의 의미와 수혜 섹터를 추론하는 고도화 연산 |
| **Agent C (편집장)** | 마크다운 리포트 조판 | **Lite 모델** | 완성된 분석 데이터를 정해진 마크다운 양식에 맞게 예쁘게 렌더링 |
| **Agent D (검수자)** | 품질 검수 및 피드백 | **Lite 모델** | 누락된 지표나 양식 오류를 찾아내 Agent C에게 반려하는 Rule-based 검토 |

> **💡 티어링 기대효과:** 가장 똑똑하고 비싼 Heavy 모델(예: Gemini 1.5/2.5 Flash)은 오직 Agent B에서만 사용(1회 실행 시 2번 호출)되므로, 일일 요청 한도(RPD)를 극적으로 아낄 수 있습니다.

---

## 🛠️ 기술 스택 (Tech Stack)

* **Language:** Python 3.11+
* **Package Manager:** `uv` (초고속 파이썬 패키지 매니저)
* **LLM API:** Google Gemini API (`google-genai`)
* **Data Sources:** `yfinance`, `feedparser`, Naver Search API, `trafilatura` (본문 크롤링)
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

---

## 디렉토리 구조

economySummary/
├── main.py            # 메인 파이프라인 오케스트레이션
├── agents.py          # 6개의 AI 에이전트 프롬프트 및 API 호출 로직
├── collectors.py      # 뉴스(Naver, RSS) 및 거시지표(yfinance) 수집기
├── memory.py          # SQLite 기반 장기 기억(Memory) 저장 및 호출 모듈 / Rule-based RAG
├── notifier.py        # Discord Webhook 전송 모듈
├── config.py          # API 키 및 환경 변수 관리
├── run_agent.sh       # Crontab 실행을 위한 Shell 스크립트
└── obsidian_notes/    # 최종 마크다운 리포트 저장 폴더

---

## API 키 및 WebHook
`.env`
```bash
GEMINI_API_KEY = "your_gemini_api_key_here"
NCP_CLIENT_ID = "your_naver_client_id_here"
NCP_CLIENT_SECRET = "your_naver_client_secret_here"
DISCORD_WEBHOOK_URL = "your_discord_webhook_url_here"
```