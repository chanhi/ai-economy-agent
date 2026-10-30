import collections
import glob
import html
import os
import re
import secrets
import time
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

import config
from config import API_KEY_NAME, OBSIDIAN_OUTPUT_DIR, SECRET_API_KEY

DAILY_ASK_LIMIT = getattr(config, "DAILY_ASK_LIMIT", 100)
from agents.core import run_rag_qa_agent
from storage.memory import (
    consume_daily_quota,
    get_daily_quota_status,
    get_macro_history,
    get_recent_pipeline_runs,
)
from storage.vector_db import get_collection, search_similar_reports

# 하위 호환 상수 별칭
OBSIDIAN_DIR = OBSIDIAN_OUTPUT_DIR

app = FastAPI(
    title="Economy Agent API",
    description="모바일 앱 연동을 위한 거시경제 리포트 및 RAG AI 비서 전용 API",
    version="2.0.0",
)

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)


def verify_api_key(api_key: str = Security(api_key_header)):
    if not SECRET_API_KEY or not secrets.compare_digest(api_key, SECRET_API_KEY):
        raise HTTPException(status_code=403, detail="권한이 없습니다. (Invalid API Key)")
    return api_key


# ---------------------------------------------------------
# 🛡️ 인메모리 Sliding-Window Rate Limiter & TTL 응답 캐시
# ---------------------------------------------------------
_RATE_BUCKETS: dict[str, collections.deque] = collections.defaultdict(collections.deque)
_QUERY_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SEC = 300  # 동일 검색/질문 5분간 캐싱하여 LLM/임베딩 API 한도 보호


def check_rate_limit(request: Request, max_requests: int = 15, window_sec: int = 60):
    client_ip = request.client.host if request.client else "local"
    key = f"{client_ip}:{request.url.path}"
    now = time.time()
    bucket = _RATE_BUCKETS[key]
    while bucket and now - bucket[0] > window_sec:
        bucket.popleft()
    if len(bucket) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail=f"요청 한도를 초과했습니다. {window_sec}초 후 다시 시도해주세요.",
        )
    bucket.append(now)


def _get_cached_response(cache_key: str) -> dict | None:
    entry = _QUERY_CACHE.get(cache_key)
    if entry and (time.time() - entry[0] < CACHE_TTL_SEC):
        return entry[1]
    if entry:
        _QUERY_CACHE.pop(cache_key, None)
    return None


def _set_cached_response(cache_key: str, payload: dict):
    if len(_QUERY_CACHE) > 200:
        oldest_key = next(iter(_QUERY_CACHE))
        _QUERY_CACHE.pop(oldest_key, None)
    _QUERY_CACHE[cache_key] = (time.time(), payload)


def _sanitize_user_text(raw: str) -> str:
    cleaned = html.escape(raw.strip()).replace("'", "").replace('"', "")
    return re.sub(r"\s+", " ", cleaned)


# ---------------------------------------------------------
# 📄 마크다운 파서 유틸리티 (기존 앱 하위 호환 100% 보장)
# ---------------------------------------------------------
def find_latest_markdown(target_keyword: str):
    """지정된 키워드('일간' 또는 '주간')가 파일명에 포함된 가장 최신 마크다운 파일을 반환"""
    list_of_files = glob.glob(f"{OBSIDIAN_OUTPUT_DIR}/**/*.md", recursive=True)
    if not list_of_files:
        return None, None

    list_of_files.sort(key=os.path.getmtime, reverse=True)

    for file_path in list_of_files:
        if target_keyword in os.path.basename(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return file_path, content

    return None, None


def _parse_markdown_table_rows(section_text: str) -> list[dict]:
    """포트폴리오 액션 플랜 마크다운 표(| 섹터 | 액션 | 핵심 근거 |)를 JSON 배열로 변환"""
    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line or "핵심 근거" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) >= 3:
            rows.append({
                "sector": cols[0],
                "action": cols[1],
                "rationale": cols[2],
            })
    return rows


def _parse_portfolio_section(portfolio_raw: str) -> dict:
    if not portfolio_raw:
        return {"raw": "", "aggressive": [], "conservative": []}

    agg_match = re.search(r"###\s*⚔️.*?\n(.*?)(?=###\s*🛡️|\Z)", portfolio_raw, re.DOTALL)
    con_match = re.search(r"###\s*🛡️.*?\n(.*?)(?=\Z)", portfolio_raw, re.DOTALL)

    return {
        "raw": portfolio_raw.strip(),
        "aggressive": _parse_markdown_table_rows(agg_match.group(1)) if agg_match else [],
        "conservative": _parse_markdown_table_rows(con_match.group(1)) if con_match else [],
    }


def _parse_sources_section(sources_raw: str) -> list[dict]:
    sources = []
    if not sources_raw:
        return sources
    for m in re.finditer(r"-\s*\[([^\]]+)\]\((https?://[^\)]+)\)", sources_raw):
        sources.append({"title": m.group(1).strip(), "url": m.group(2).strip()})
    return sources


def parse_daily_markdown_to_json(file_path: str, content: str):
    """[일간 리포트 전용] 기존 필드 호환성을 100% 유지하면서 포트폴리오·출처·투심 데이터를 구조화 파싱"""
    try:
        date_match = re.search(r"date:\s*(.+)", content)
        market_phase_match = re.search(r"market_phase:\s*(.+)", content)
        sentiment_score_match = re.search(r"sentiment_score:\s*(\d+)", content)
        sentiment_label_match = re.search(r"sentiment_label:\s*(.+)", content)

        desk_summary_match = re.search(r">\s*\*\*💡 Desk's Executive Summary:\*\*\s*(.+)", content)
        # 💡 신규 'Editor's Deep Dive Summary'와 구버전 'Editor's Insight' 양방향 호환
        editor_insight_match = re.search(
            r">\s*\*\*(?:💡 Editor's Deep Dive Summary|🎯 Editor's Insight):\*\*\s*(.+)",
            content,
        )

        macro_section = re.search(
            r"## 📊 글로벌 매크로 지표 브리핑\n(.*?)(?=## 📑|## 📖|## 🔗|## 🧭|$)",
            content,
            re.DOTALL,
        )
        macro_text = macro_section.group(1).strip() if macro_section else ""

        news_section = re.search(
            r"## 📑 심층 분석 리포트.*?\n(.*?)(?=## 📖|## 🔗|## 🧭|$)",
            content,
            re.DOTALL,
        )
        news_text = news_section.group(1).strip() if news_section else ""

        terms_section = re.search(
            r"## 📖 오늘의 금융/경제 단어장\n(.*?)(?=## 🔗|## 🧭|$)",
            content,
            re.DOTALL,
        )
        terms_text = terms_section.group(1).strip() if terms_section else ""

        sources_section = re.search(
            r"## 🔗 출처 및 참고 기사\n(.*?)(?=## 🧭|$)",
            content,
            re.DOTALL,
        )
        sources_raw = sources_section.group(1).strip() if sources_section else ""

        portfolio_section = re.search(
            r"## 🧭 일간 포트폴리오 액션 플랜.*?\n(.*?)(?=$)",
            content,
            re.DOTALL,
        )
        portfolio_raw = portfolio_section.group(1).strip() if portfolio_section else ""

        sentiment_score = int(sentiment_score_match.group(1)) if sentiment_score_match else None
        sentiment_label = sentiment_label_match.group(1).strip() if sentiment_label_match else None

        return {
            "report_type": "daily",
            "file_name": os.path.basename(file_path),
            "date": date_match.group(1).strip() if date_match else datetime.today().strftime("%Y-%m-%d"),
            "market_phase": market_phase_match.group(1).strip() if market_phase_match else "Unknown",
            "sentiment": {
                "score": sentiment_score,
                "label": sentiment_label,
            },
            "insights": {
                "desk_summary": desk_summary_match.group(1).strip() if desk_summary_match else "",
                "editor_insight": editor_insight_match.group(1).strip() if editor_insight_match else "",
            },
            "macro_indicators": macro_text,
            "news_analysis": news_text,
            "terms": terms_text,
            "sources": _parse_sources_section(sources_raw),
            "portfolio_plan": _parse_portfolio_section(portfolio_raw),
        }
    except Exception as e:
        return {
            "report_type": "daily",
            "file_name": os.path.basename(file_path),
            "date": datetime.today().strftime("%Y-%m-%d"),
            "parse_error": str(e),
        }


def parse_weekly_markdown_to_json(file_path: str, content: str):
    """[주간 결산 리포트 전용] 마크다운 본문을 파싱"""
    try:
        date_match = re.search(r"date:\s*(.+)", content)
        chief_insight_match = re.search(r">\s*\*\*💡 Chief's Insight:\*\*\s*(.+)", content)
        chief_insight = chief_insight_match.group(1).strip() if chief_insight_match else ""

        themes_section = re.search(
            r"## 🌊 주간 핵심 테마 내러티브.*?\n(.*?)(?=## 📊|## 🎯|## 🔮|$)",
            content,
            re.DOTALL,
        )
        macro_section = re.search(
            r"## 📊 주요 매크로 지표 및 이벤트 리뷰\n(.*?)(?=## 🎯|## 🔮|$)",
            content,
            re.DOTALL,
        )
        sector_section = re.search(
            r"## 🎯 수혜/피해 주요 섹터 결산\n(.*?)(?=## 🔮|$)",
            content,
            re.DOTALL,
        )
        watchpoints_section = re.search(
            r"## 🔮 다음 주 시장 관전 포인트.*?\n(.*?)(?=$)",
            content,
            re.DOTALL,
        )

        return {
            "report_type": "weekly",
            "file_name": os.path.basename(file_path),
            "date": date_match.group(1).strip() if date_match else datetime.today().strftime("%Y-%m-%d"),
            "insights": {
                "chief_insight": chief_insight,
            },
            "core_themes": themes_section.group(1).strip() if themes_section else "",
            "macro_review": macro_section.group(1).strip() if macro_section else "",
            "sector_summary": sector_section.group(1).strip() if sector_section else "",
            "watchpoints": watchpoints_section.group(1).strip() if watchpoints_section else "",
        }
    except Exception as e:
        return {
            "report_type": "weekly",
            "file_name": os.path.basename(file_path),
            "date": datetime.today().strftime("%Y-%m-%d"),
            "parse_error": str(e),
        }


def parse_markdown_by_type(file_path: str, content: str):
    if "주간" in os.path.basename(file_path):
        return parse_weekly_markdown_to_json(file_path, content)
    return parse_daily_markdown_to_json(file_path, content)


# ---------------------------------------------------------
# 🌐 REST API 엔드포인트
# ---------------------------------------------------------
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Economy Agent API Server v2.0 is running 🚀"}


@app.get("/api/health")
def get_system_health(api_key: str = Depends(verify_api_key)):
    """파이프라인 최근 실행 상태 및 Vector DB 적재 현황 모니터링"""
    try:
        vector_count = get_collection().count()
    except Exception:
        vector_count = -1

    return {
        "status": "ok",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "vector_chunks_count": vector_count,
        "ask_daily_quota": get_daily_quota_status("ask", DAILY_ASK_LIMIT),
        "recent_runs": get_recent_pipeline_runs(limit=5),
    }


@app.get("/api/report/today")
def get_daily_report(api_key: str = Depends(verify_api_key)):
    """모바일 앱 용: 가장 최신 일간 거시경제 리포트 조회"""
    file_path, content = find_latest_markdown("일간")
    if not file_path:
        raise HTTPException(status_code=404, detail="일간 리포트를 찾을 수 없습니다.")
    return parse_markdown_by_type(file_path, content)


@app.get("/api/report/weekly")
def get_weekly_report(api_key: str = Depends(verify_api_key)):
    """모바일 앱 용: 가장 최신 주간 결산 리포트 조회"""
    file_path, content = find_latest_markdown("주간")
    if not file_path:
        raise HTTPException(status_code=404, detail="주간 리포트를 찾을 수 없습니다.")
    return parse_markdown_by_type(file_path, content)


@app.get("/api/reports")
def list_reports(
    request: Request,
    report_type: str = Query("all", pattern="^(all|daily|weekly)$", description="조회할 리포트 종류"),
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$", description="필터링할 연-월 (예: 2026-10)"),
    limit: int = Query(20, ge=1, le=100, description="반환할 최대 리포트 수"),
    offset: int = Query(0, ge=0, description="페이지네이션 오프셋"),
    api_key: str = Depends(verify_api_key),
):
    """모바일 앱 아카이브/캘린더 탭 용: 리포트 목록 메타데이터 조회 (대량 스크래핑 방지 Rate Limit 적용)"""
    check_rate_limit(request, max_requests=15, window_sec=60)
    search_root = os.path.join(OBSIDIAN_OUTPUT_DIR, month) if month else OBSIDIAN_OUTPUT_DIR
    if not os.path.exists(search_root):
        return {"status": "ok", "total": 0, "items": []}

    all_files = glob.glob(f"{search_root}/**/*.md", recursive=True)
    filtered = []
    for fp in all_files:
        fname = os.path.basename(fp)
        is_weekly = "주간" in fname
        is_daily = "일간" in fname
        if report_type == "daily" and not is_daily:
            continue
        if report_type == "weekly" and not is_weekly:
            continue
        filtered.append(fp)

    filtered.sort(key=lambda p: os.path.basename(p)[:10], reverse=True)
    sliced = filtered[offset : offset + limit]

    items = []
    abs_obs = os.path.abspath(OBSIDIAN_OUTPUT_DIR)
    for fp in sliced:
        fname = os.path.basename(fp)
        rel_path = os.path.relpath(os.path.abspath(fp), abs_obs)
        # 파일명에서 키워드 추출 (예: 2026-10-30_키워드_일간_종합_경제요약.md)
        parts = fname.replace(".md", "").split("_")
        keyword = parts[1] if len(parts) >= 3 else fname
        items.append({
            "report_type": "weekly" if "주간" in fname else "daily",
            "date": fname[:10],
            "keyword": keyword,
            "file_name": fname,
            "rel_path": rel_path,
        })

    return {
        "status": "ok",
        "total": len(filtered),
        "count": len(items),
        "items": items,
    }


@app.get("/api/macro/history")
def macro_history_endpoint(
    days: int = Query(30, ge=1, le=90, description="조회할 최근 일수 (최대 90일)"),
    api_key: str = Depends(verify_api_key),
):
    """모바일 앱 대시보드 차트 용: 최근 N일 거시 지표 및 시장 심리 시계열 데이터 조회"""
    points = get_macro_history(days=days)
    return {
        "status": "ok",
        "days": days,
        "count": len(points),
        "history": points,
    }


@app.get("/api/report/detail")
def get_report_detail(
    request: Request,
    path: str = Query(..., description="조회할 리포트의 상대 경로 (예: 2026-10/2026-10-08_일간_종합_경제요약.md)"),
    api_key: str = Depends(verify_api_key),
):
    """모바일 앱 용: 검색 결과 또는 목록에서 선택한 특정 원문 리포트 상세 조회 (대량 스크래핑 방지 Rate Limit 적용)"""
    check_rate_limit(request, max_requests=15, window_sec=60)
    try:
        safe_path = os.path.normpath(path)
        if safe_path.startswith("..") or os.path.isabs(safe_path):
            raise HTTPException(status_code=400, detail="잘못된 경로 접근입니다.")

        abs_obs = os.path.abspath(OBSIDIAN_OUTPUT_DIR)
        file_path = os.path.abspath(os.path.join(abs_obs, safe_path))
        if not file_path.startswith(abs_obs + os.sep):
            raise HTTPException(status_code=400, detail="잘못된 경로 접근입니다.")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="원문 리포트 파일을 찾을 수 없습니다.")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return parse_markdown_by_type(file_path, content)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 원문 조회 중 오류가 발생했습니다: {str(e)}")


@app.get("/api/search")
def search_reports(
    request: Request,
    q: str = Query(..., min_length=2, max_length=50, description="검색할 자연어 질문 (최대 50자 제한)"),
    top_k: int = Query(5, ge=1, le=20, description="반환할 최대 결과 개수"),
    api_key: str = Depends(verify_api_key),
):
    """모바일 앱 용: Vector DB 기반 과거 리포트 의미 검색 (Semantic Search)"""
    check_rate_limit(request, max_requests=20, window_sec=60)
    try:
        safe_q = _sanitize_user_text(q)
        cache_key = f"search:{safe_q}:{top_k}"
        cached = _get_cached_response(cache_key)
        if cached is not None:
            return cached

        results = search_similar_reports(query=safe_q, top_k=top_k)
        payload = {
            "status": "ok",
            "query": safe_q,
            "count": len(results),
            "results": results,
        }
        _set_cached_response(cache_key, payload)
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 처리 중 오류가 발생했습니다: {str(e)}")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=120, description="거시경제/시장 흐름에 대한 자연어 질문")
    top_k: int = Field(default=5, ge=1, le=10, description="참조할 과거 리포트 청크 수")


@app.post("/api/ask")
def ask_macro_assistant(
    body: AskRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """모바일 앱 용: 과거 리포트 Vector DB를 근거로 답변하는 인터랙티브 RAG Q&A 챗봇 (서버 전체 일 100회 상한)"""
    check_rate_limit(request, max_requests=10, window_sec=60)
    try:
        safe_q = _sanitize_user_text(body.question)
        cache_key = f"ask:{safe_q}:{body.top_k}"
        cached = _get_cached_response(cache_key)
        if cached is not None:
            quota = get_daily_quota_status("ask", DAILY_ASK_LIMIT)
            return {**cached, "daily_quota": quota}

        allowed, used_count = consume_daily_quota("ask", DAILY_ASK_LIMIT)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"서버 전체 일일 AI Q&A 한도({DAILY_ASK_LIMIT}회)가 모두 소진되었습니다. 내일 다시 이용해 주세요.",
            )

        retrieved = search_similar_reports(query=safe_q, top_k=body.top_k)
        qa_result = run_rag_qa_agent(safe_q, retrieved)

        citations = [
            {
                "date": r["date"],
                "title": r["title"],
                "market_phase": r["market_phase"],
                "similarity": r["similarity"],
                "rel_path": r["rel_path"],
            }
            for r in retrieved
        ]
        quota_info = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "limit": DAILY_ASK_LIMIT,
            "used": used_count,
            "remaining": max(0, DAILY_ASK_LIMIT - used_count),
        }
        payload = {
            "status": "ok",
            "question": safe_q,
            "answer": qa_result.get("answer", ""),
            "key_points": qa_result.get("key_points", []),
            "citations": citations,
            "daily_quota": quota_info,
        }
        _set_cached_response(cache_key, payload)
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 답변 생성 중 오류가 발생했습니다: {str(e)}")
