# 📱 Economy Agent REST API v2.0 명세서 (모바일 앱 연동용)

본 문서는 [server.py](file:///home/chan/economySummary/server.py) v2.0 기준 모바일 앱 클라이언트 연동을 위한 공식 API 명세입니다. 기존 앱 코드가 깨지지 않도록 **하위 호환성(Backward Compatibility)을 100% 보장**하며, 신규 필드와 엔드포인트가 확장(Additive) 방식으로 추가되었습니다.

---

## 1. 공통 규칙 (Authentication, Rate Limit & Errors)

### 1.1 인증 헤더 (필수)
`GET /` 루트 확인을 제외한 모든 `/api/*` 요청에는 HTTP 헤더에 API 키를 포함해야 합니다.
```http
X-API-Key: <APP_SECRET_API_KEY>
Content-Type: application/json
```
*(헤더 키 이름은 서버 `.env`의 `APP_API_KEY_NAME` 설정을 따르며 기본값은 `X-API-Key`입니다.)*

### 1.2 공통 HTTP 상태 코드
| 상태 코드 | 의미 | 발생 조건 및 앱 처리 가이드 |
| :---: | :--- | :--- |
| `200` | 정상 응답 | JSON 본문 파싱 |
| `400` | 잘못된 요청 | `path` 파라미터 경로 조작 시도(`..` 또는 절대경로) |
| `403` | 인증 실패 | `X-API-Key` 누락 또는 불일치 (`{"detail": "권한이 없습니다. (Invalid API Key)"}`) |
| `404` | 리포트 없음 | 해당 조건의 일간/주간/상세 마크다운 파일이 존재하지 않음 |
| `422` | 파라미터 검증 실패 | 검색어 글자 수 미달/초과(`q`: 2~50자, `question`: 2~120자), `month` 포맷(`YYYY-MM`) 불일치 등 |
| `429` | 요청 한도 초과 | `/api/reports`·`/api/report/detail`(분당 15회), `/api/search`(분당 20회), `/api/ask`(분당 10회 및 **서버 전체 일일 100회 상한**) 초과 시 반환 — 토스트 안내 후 재시도 유도 |
| `500` | 서버 내부 오류 | 파일 읽기 또는 외부 임베딩/LLM 처리 중 예외 발생 |

> [!TIP]
> **서버 측 캐싱 안내**: `/api/search`와 `/api/ask`는 동일 질문에 대해 서버 메모리에 **5분(300초)간 응답을 캐싱**하므로, 사용자가 같은 질문을 재조회할 때 즉시(`0.01초`) 응답하며 API 한도를 소모하지 않습니다.

---

## 2. 엔드포인트 전체 요약

| 구분 | Method & Path | 설명 | 비고 |
| :---: | :--- | :--- | :--- |
| 기존 확장 | `GET /api/report/today` | 최신 일간 종합 리포트 조회 | **`sentiment`, `sources`, `portfolio_plan` 추가 + `editor_insight` 파싱 복구** |
| 기존 유지 | `GET /api/report/weekly` | 최신 주간 총결산 리포트 조회 | 기존 스키마 동일 |
| 기존 개선 | `GET /api/report/detail` | 특정 과거 리포트 원문 상세 조회 | 일간/주간 자동 판별 + Rate Limit(15/min) |
| 기존 개선 | `GET /api/search` | Vector DB 의미 기반 검색 | Rate Limit(20/min) + 5분 캐시 추가 |
| **신규** | `GET /api/reports` | 월별/종류별 리포트 아카이브 목록 조회 | 앱 내 **캘린더 / 히스토리 탭** 구현용 (Rate Limit 15/min) |
| **신규** | `GET /api/macro/history` | 최근 N일 거시 지표 & 투심 시계열 조회 | 앱 내 **미니 차트(Sparkline)** 구현용 |
| **신규** | `POST /api/ask` | 과거 리포트 근거 기반 RAG AI Q&A 챗봇 | 답변 + 핵심 요약 + 원문 인용(`citations`) 반환 (서버 전체 일 100회 상한) |
| **신규** | `GET /api/health` | 서버·Vector DB·최근 배치 상태 조회 | 앱 설정/진단 화면용 |

---

## 3. 엔드포인트별 상세 명세

### 3.1 최신 일간 리포트 조회 (확장됨)
* **URL**: `GET /api/report/today`
* **변경 포인트**:
  1. 기존에 빈 문자열로 내려오던 `insights.editor_insight`가 정상 반환됩니다.
  2. `sentiment` (시장 심리 온도 `0~100` 및 라벨; 구버전 리포트는 `null`) 필드가 추가되었습니다.
  3. `sources` (원문 기사 제목·링크 배열) 필드가 추가되었습니다.
  4. `portfolio_plan` (공격투자형/안정투자형 7대 섹터 액션 플랜 구조화 배열) 필드가 추가되었습니다.

#### Response `200 OK`
```json
{
  "report_type": "daily",
  "file_name": "2026-10-30_AI투자우려_일간_종합_경제요약.md",
  "date": "2026-10-30",
  "market_phase": "Bear",
  "sentiment": {
    "score": 35,
    "label": "공포"
  },
  "insights": {
    "desk_summary": "구글 모회사 [[알파벳]]의 실적 부진과 자본지출 확대 여파로 [[뉴욕증시]]가 일제히 하락한 가운데...",
    "editor_insight": "최근 [[알파벳]]과 [[아마존]] 등 글로벌 [[빅테크]] 기업들의 실적 부진 및 [[AI]] 인프라 투자 비용 급증 우려가..."
  },
  "macro_indicators": "- **S&P 500**: 7,720.39 (-0.30%) 기록...\n- **코스피**: 5,759.14 (-3.01%) 기록...",
  "news_analysis": "### 1. 이형일 \"취약차주 추가 대책 마련…\"\n- **선정 이유**: ...",
  "terms": "- **[[T+1 결제주기]]**: 주식을 매수한 날로부터...",
  "sources": [
    {
      "title": "이형일 \"취약차주 추가 대책 마련…주식 결제주기 단축 의견수렴\"",
      "url": "https://www.newsis.com/view/NISX20261029_0003845995"
    }
  ],
  "portfolio_plan": {
    "raw": "### ⚔️ 공격투자형 (Aggressive)\n| 섹터 | 액션 | 핵심 근거 |...",
    "aggressive": [
      {
        "sector": "대형 기술주",
        "action": "축소",
        "rationale": "빅테크 CAPEX 과다 지출 대비 AI 수익화 지연 및 실적 가이던스 둔화로 추가 조정 불가피"
      },
      {
        "sector": "헬스케어",
        "action": "확대",
        "rationale": "기술주 이탈 자금의 유입에 따른 호실적 기반 방어형 순환매 수혜 기대"
      }
    ],
    "conservative": [
      {
        "sector": "미국 장기 국채",
        "action": "확대",
        "rationale": "4.98%대 고금리 채권 편입을 통한 확정 이자 확보 및 증시 충격 완화 효과 극대화"
      }
    ]
  }
}
```

---

### 3.2 리포트 아카이브 목록 조회 (신규)
* **URL**: `GET /api/reports`
* **용도**: 과거 발행된 일간/주간 리포트 목록을 페이지네이션 또는 연-월 단위로 불러오고, 항목 클릭 시 `rel_path`를 `GET /api/report/detail?path={rel_path}`에 넘겨 상세 화면으로 이동합니다.
* **Query Parameters**:
  * `report_type` *(optional, default `"all"`)*: `"all"` | `"daily"` | `"weekly"`
  * `month` *(optional)*: `"YYYY-MM"` 형식 필터 (예: `"2026-10"`)
  * `limit` *(optional, default `20`)*: `1 ~ 100`
  * `offset` *(optional, default `0`)*: `0` 이상 정수

#### Response `200 OK`
```json
{
  "status": "ok",
  "total": 28,
  "count": 2,
  "items": [
    {
      "report_type": "daily",
      "date": "2026-10-30",
      "keyword": "연준 금리 동결과 AI 빅테크 실적 장세",
      "file_name": "2026-10-30_연준 금리 동결과 AI 빅테크 실적 장세_일간_종합_경제요약.md",
      "rel_path": "2026-10/2026-10-30_연준 금리 동결과 AI 빅테크 실적 장세_일간_종합_경제요약.md"
    },
    {
      "report_type": "weekly",
      "date": "2026-10-W4",
      "keyword": "주간",
      "file_name": "2026-10-W4_주간_경제_총결산.md",
      "rel_path": "2026-10/2026-10-W4_주간_경제_총결산.md"
    }
  ]
}
```

---

### 3.3 거시 지표 & 시장 심리 시계열 조회 (신규)
* **URL**: `GET /api/macro/history`
* **용도**: 모바일 대시보드 상단에 최근 7일/30일/90일 **S&P 500, 코스피, 원/달러 환율, 미 10년물 국채금리, VIX, 시장 심리 온도** 라인 차트(Sparkline)를 렌더링합니다.
  * 기존 DB에 저장된 과거 데이터는 4대 지표(`S&P 500`, `원/달러 환율`, `미국 10년물 국채금리`, `WTI 원유`)의 `value`가 자동 파싱되어 즉시 차트로 그릴 수 있으며, v2.0 이후 저장분부터는 8대 지표 전체(`나스닥`, `코스피`, `VIX 변동성 지수`, `국제 금` 포함) 및 `change_1d_pct`, `change_5d_pct`, `sentiment_score`가 함께 채워집니다.
* **Query Parameters**:
  * `days` *(optional, default `30`)*: `1 ~ 90` (오래된 날짜 ➔ 최신 날짜 오름차순 정렬 반환)

#### Response `200 OK`
```json
{
  "status": "ok",
  "days": 30,
  "count": 30,
  "history": [
    {
      "date": "2026-10-29",
      "keyword": "앤트로픽 IPO 및 AI 반도체 훈풍",
      "sentiment_score": null,
      "metrics": {
        "S&P 500": {
          "value": 7743.98,
          "display": "7,743.98"
        },
        "원/달러 환율": {
          "value": 1342.47,
          "display": "1,342.47원"
        }
      },
      "raw_summary": "S&P 500: 7,743.98 | 원/달러 환율: 1,342.47원 | 미국 10년물 국채금리: 5.045% | WTI 원유: $101.94"
    },
    {
      "date": "2026-10-30",
      "keyword": "AI투자우려",
      "sentiment_score": 35,
      "metrics": {
        "S&P 500": {
          "ticker": "^GSPC",
          "value": 7720.39,
          "display": "7,720.39 (-0.30%, 5일 +1.27%)",
          "change_1d_pct": -0.3,
          "change_5d_pct": 1.27
        },
        "코스피": {
          "ticker": "^KS11",
          "value": 5759.14,
          "display": "5,759.14 (-3.01%, 5일 +5.30%)",
          "change_1d_pct": -3.01,
          "change_5d_pct": 5.3
        }
      },
      "raw_summary": "S&P 500: 7,720.39 (-0.30%, 5일 +1.27%) | ..."
    }
  ]
}
```

---

### 3.4 인터랙티브 거시경제 AI 비서 — RAG Q&A (신규)
* **URL**: `POST /api/ask`
* **용도**: 앱 사용자가 자연어로 질문하면 ChromaDB에서 가장 유사한 과거 리포트 청크를 검색한 뒤, 근거 기반 요약 답변(`answer`), 핵심 불릿(`key_points`), 근거 리포트 목록(`citations`)을 반환합니다. `citations[].rel_path`를 누르면 `GET /api/report/detail?path={rel_path}`로 원문 리포트 열람이 가능합니다.
* **Rate Limit & 일일 쿼터**:
  * **단기 제한**: IP당 분당 최대 10회 (`429 Too Many Requests`)
  * **서버 전체 일일 상한**: 하루 최대 **100회** (`DAILY_ASK_LIMIT`, SQLite 영속 저장으로 서버 재시작 시에도 유지되며 매일 `00:00` 자동 초기화 / 5분 내 동일 질문 캐시 응답은 차감되지 않음). 초과 시 `429` 반환 (`{"detail": "서버 전체 일일 AI Q&A 한도(100회)가 모두 소진되었습니다. 내일 다시 이용해 주세요."}`)

#### Request Body (`application/json`)
```json
{
  "question": "최근 빅테크 CapEx 확대 우려가 반도체 섹터에 미친 영향은?",
  "top_k": 5
}
```
* `question` *(required)*: `2 ~ 120`자 문자열
* `top_k` *(optional, default `5`)*: `1 ~ 10` 정수

#### Response `200 OK`
```json
{
  "status": "ok",
  "question": "최근 빅테크 CapEx 확대 우려가 반도체 섹터에 미친 영향은?",
  "answer": "최근 구글(알파벳)과 메타 등 주요 빅테크 기업들의 막대한 AI 설비투자(CapEx) 대비 수익화 지연 우려가 불거지면서 기술주 전반의 현금 소진(Cash Burn) 경계감이 높아졌습니다. 다만 핵심 자본재 주문 급증과 오라클·SK하이닉스의 호실적에서 확인되듯 AI 인프라 실수요는 견조하여, 레거시 반도체(인텔 등)와 HBM 중심 AI 반도체 간 실적 차별화가 극대화되는 흐름입니다.",
  "key_points": [
    "빅테크의 과도한 AI CapEx 지출로 단기 현금흐름(FCF) 검증 장세 돌입",
    "인텔 등 레거시 IT 하드웨어 급락 vs HBM·AI 인프라 주도주 강세 양극화",
    "향후 컨퍼런스콜 내 CapEx 가이던스 및 ROI 입증 여부가 핵심 변수"
  ],
  "citations": [
    {
      "date": "2026-10-30",
      "title": "Google shares tumble 9% after $51bn AI outlay deepens cash burn",
      "market_phase": "Sideways",
      "similarity": 86.4,
      "rel_path": "2026-10/2026-10-30_연준 금리 동결과 AI 빅테크 실적 장세_일간_종합_경제요약.md"
    }
  ],
  "daily_quota": {
    "date": "2026-10-30",
    "limit": 100,
    "used": 12,
    "remaining": 88
  }
}
```

---

### 3.5 기타 엔드포인트 (기존 유지 및 시스템 헬스체크)

#### `GET /api/report/weekly`
* 최신 주간 리포트를 반환합니다 (`report_type: "weekly"`, `file_name`, `date`, `insights.chief_insight`, `core_themes`, `macro_review`, `sector_summary`, `watchpoints`).

#### `GET /api/report/detail?path={rel_path}`
* `path`: `/api/search`, `/api/ask`, `/api/reports`에서 받은 `rel_path` 값을 URL 인코딩하여 전달합니다.
* 파일명에 `"주간"`이 포함되면 주간 JSON 스키마로, 그 외에는 일간 JSON 스키마(3.1절과 동일)로 응답합니다.

#### `GET /api/search?q={query}&top_k={top_k}`
* `q`: `2 ~ 50`자 검색어, `top_k`: `1 ~ 20` (기본 `5`), 분당 20회 제한.
* 응답: `{"status": "ok", "query": "...", "count": 5, "results": [{"id", "date", "keyword", "market_phase", "title", "type", "filename", "rel_path", "similarity", "content"}]}`.

#### `GET /api/health` (신규)
* 서버 상태, ChromaDB 총 저장 청크 수, 당일 AI Q&A 잔여 쿼터(`ask_daily_quota`), 최근 5회 배치 실행 결과를 반환합니다.
```json
{
  "status": "ok",
  "timestamp": "2026-10-30 14:35:00",
  "vector_chunks_count": 612,
  "ask_daily_quota": {
    "date": "2026-10-30",
    "limit": 100,
    "used": 12,
    "remaining": 88
  },
  "recent_runs": [
    {
      "pipeline_name": "daily_pipeline",
      "started_at": "2026-10-30 07:00:01",
      "finished_at": "2026-10-30 07:12:44",
      "duration_sec": 763.12,
      "status": "success",
      "articles_processed": 10,
      "fallback_count": 1,
      "notes": "키워드:AI투자우려 | 본문크롤링:4/10 | 투심:35"
    }
  ]
}
```

---

## 4. Android (Kotlin + Retrofit) 연동 코드 템플릿

안드로이드 프로젝트에 그대로 복사해 넣거나 앱 개발 에이전트 프롬프트에 바로 전달할 수 있는 DTO 및 Retrofit 인터페이스 예시입니다.

```kotlin
package com.example.economyagent.data.remote

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

// 1. 일간 리포트 응답 DTO (구버전 리포트 호환을 위해 신규 필드는 Nullable/기본값 처리)
data class DailyReportResponse(
    val report_type: String,
    val file_name: String,
    val date: String,
    val market_phase: String,
    val sentiment: SentimentDto? = null,
    val insights: DailyInsightsDto,
    val macro_indicators: String = "",
    val news_analysis: String = "",
    val terms: String = "",
    val sources: List<ArticleSourceDto> = emptyList(),
    val portfolio_plan: PortfolioPlanDto? = null
)

data class SentimentDto(
    val score: Int? = null,
    val label: String? = null
)

data class DailyInsightsDto(
    val desk_summary: String = "",
    val editor_insight: String = ""
)

data class ArticleSourceDto(
    val title: String,
    val url: String
)

data class PortfolioPlanDto(
    val raw: String = "",
    val aggressive: List<SectorActionDto> = emptyList(),
    val conservative: List<SectorActionDto> = emptyList()
)

data class SectorActionDto(
    val sector: String,
    val action: String,     // "확대" | "유지" | "축소"
    val rationale: String
)

// 2. 리포트 목록 (/api/reports) DTO
data class ReportListResponse(
    val status: String,
    val total: Int = 0,
    val count: Int = 0,
    val items: List<ReportListItemDto> = emptyList()
)

data class ReportListItemDto(
    val report_type: String, // "daily" | "weekly"
    val date: String,
    val keyword: String,
    val file_name: String,
    val rel_path: String
)

// 3. 거시 지표 시계열 (/api/macro/history) DTO
data class MacroHistoryResponse(
    val status: String,
    val days: Int,
    val count: Int,
    val history: List<MacroHistoryPointDto> = emptyList()
)

data class MacroHistoryPointDto(
    val date: String,
    val keyword: String?,
    val sentiment_score: Int? = null,
    val metrics: Map<String, MacroMetricValueDto> = emptyMap(),
    val raw_summary: String = ""
)

data class MacroMetricValueDto(
    val ticker: String? = null,
    val value: Double,
    val display: String = "",
    val change_1d_pct: Double? = null,
    val change_5d_pct: Double? = null
)

// 4. RAG AI 비서 (/api/ask) 요청/응답 DTO
data class AskRequestDto(
    val question: String,
    val top_k: Int = 5
)

data class AskResponseDto(
    val status: String,
    val question: String,
    val answer: String,
    val key_points: List<String> = emptyList(),
    val citations: List<CitationDto> = emptyList(),
    val daily_quota: DailyQuotaDto? = null
)

data class DailyQuotaDto(
    val date: String,
    val limit: Int,
    val used: Int,
    val remaining: Int
)

data class CitationDto(
    val date: String,
    val title: String,
    val market_phase: String,
    val similarity: Double,
    val rel_path: String
)

// 5. Retrofit 인터페이스 (OkHttp Interceptor에서 X-API-Key 헤더 일괄 주입 권장)
interface EconomyApiService {

    @GET("/api/report/today")
    suspend fun getTodayReport(): DailyReportResponse

    @GET("/api/reports")
    suspend fun getReportList(
        @Query("report_type") reportType: String = "all",
        @Query("month") month: String? = null,
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0
    ): ReportListResponse

    @GET("/api/macro/history")
    suspend fun getMacroHistory(
        @Query("days") days: Int = 30
    ): MacroHistoryResponse

    @POST("/api/ask")
    suspend fun askAssistant(
        @Body body: AskRequestDto
    ): AskResponseDto
}
```
