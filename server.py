import glob
import os
import re
import html
from datetime import datetime
from config import API_KEY_NAME, SECRET_API_KEY
from fastapi import FastAPI, HTTPException, Security, Depends, Query
from fastapi.security import APIKeyHeader
from storage.vector_db import search_similar_reports

# 옵시디언 마크다운 리포트 저장 절대 경로
OBSIDIAN_DIR = "/home/chan/economySummary/obsidian_notes"

# FastAPI 앱 생성
app = FastAPI(
    title="Economy Agent API",
    description="모바일 앱 연동을 위한 거시경제 리포트 전용 API",
    version="1.2.0"
)

# 💡 1. API 키 설정
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != SECRET_API_KEY:
        raise HTTPException(status_code=403, detail="권한이 없습니다. (Invalid API Key)")
    return api_key

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Economy Agent API Server is running 🚀"}

def find_latest_markdown(target_keyword: str):
    """지정된 키워드(예: '일간', '주간')가 '파일명'에 포함된 가장 최신 마크다운 파일을 반환"""
    list_of_files = glob.glob(f"{OBSIDIAN_DIR}/**/*.md", recursive=True)
    if not list_of_files:
        return None, None
    
    # 수정 시간 기준 내림차순 정렬 (최신 파일이 먼저 오도록)
    list_of_files.sort(key=os.path.getmtime, reverse=True)
    
    for file_path in list_of_files:
        file_name = os.path.basename(file_path)
        
        if target_keyword in file_name:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return file_path, content
                
    return None, None

def parse_daily_markdown_to_json(file_path: str, content: str):
    """[일간 리포트 전용] 마크다운 본문을 파싱"""
    try:
        date_match = re.search(r"date:\s*(.+)", content)
        market_phase_match = re.search(r"market_phase:\s*(.+)", content)
        
        desk_summary_match = re.search(r">\s*\*\*💡 Desk's Executive Summary:\*\*\s*(.+)", content)
        editor_insight_match = re.search(r">\s*\*\*🎯 Editor's Insight:\*\*\s*(.+)", content)
        
        macro_section = re.search(r"## 📊 글로벌 매크로 지표 브리핑\n(.*?)(?=## 📑|## 📖|## 🔗|$)", content, re.DOTALL)
        macro_text = macro_section.group(1).strip() if macro_section else ""
        
        news_section = re.search(r"## 📑 심층 분석 리포트.*?\n(.*?)(?=## 📖|## 🔗|$)", content, re.DOTALL)
        news_text = news_section.group(1).strip() if news_section else ""

        terms_section = re.search(r"## 📖 오늘의 금융/경제 단어장\n(.*?)(?=## 🔗|$)", content, re.DOTALL)
        terms_text = terms_section.group(1).strip() if terms_section else ""

        return {
            "report_type": "daily",
            "file_name": os.path.basename(file_path),
            "date": date_match.group(1).strip() if date_match else datetime.today().strftime("%Y-%m-%d"),
            "market_phase": market_phase_match.group(1).strip() if market_phase_match else "Unknown",
            "insights": {
                "desk_summary": desk_summary_match.group(1).strip() if desk_summary_match else "",
                "editor_insight": editor_insight_match.group(1).strip() if editor_insight_match else ""
            },
            "macro_indicators": macro_text,
            "news_analysis": news_text,
            "terms": terms_text
        }
    except Exception as e:
        return {
            "report_type": "daily",
            "file_name": os.path.basename(file_path),
            "date": datetime.today().strftime("%Y-%m-%d"),
            "parse_error": str(e)
        }

def parse_weekly_markdown_to_json(file_path: str, content: str):
    """[주간 결산 리포트 전용] 마크다운 본문을 파싱"""
    try:
        # 프론트매터 파싱
        date_match = re.search(r"date:\s*(.+)", content)
        
        # Chief's Insight 파싱
        chief_insight_match = re.search(r">\s*\*\*💡 Chief's Insight:\*\*\s*(.+)", content)
        chief_insight = chief_insight_match.group(1).strip() if chief_insight_match else ""
        
        # 주간 핵심 테마 내러티브 파싱
        themes_section = re.search(r"## 🌊 주간 핵심 테마 내러티브.*?\n(.*?)(?=## 📊|## 🎯|## 🔮|$)", content, re.DOTALL)
        themes_text = themes_section.group(1).strip() if themes_section else ""
        
        # 주요 매크로 지표 및 이벤트 리뷰 파싱
        macro_section = re.search(r"## 📊 주요 매크로 지표 및 이벤트 리뷰\n(.*?)(?=## 🎯|## 🔮|$)", content, re.DOTALL)
        macro_text = macro_section.group(1).strip() if macro_section else ""

        # 수혜/피해 주요 섹터 결산 파싱 (마크다운 표 형태)
        sector_section = re.search(r"## 🎯 수혜/피해 주요 섹터 결산\n(.*?)(?=## 🔮|$)", content, re.DOTALL)
        sector_text = sector_section.group(1).strip() if sector_section else ""

        # 다음 주 시장 관전 포인트 파싱
        watchpoints_section = re.search(r"## 🔮 다음 주 시장 관전 포인트.*?\n(.*?)(?=$)", content, re.DOTALL)
        watchpoints_text = watchpoints_section.group(1).strip() if watchpoints_section else ""

        return {
            "report_type": "weekly",
            "file_name": os.path.basename(file_path),
            "date": date_match.group(1).strip() if date_match else datetime.today().strftime("%Y-%m-%d"),
            "insights": {
                "chief_insight": chief_insight
            },
            "core_themes": themes_text,
            "macro_review": macro_text,
            "sector_summary": sector_text,
            "watchpoints": watchpoints_text
        }
    except Exception as e:
        return {
            "report_type": "weekly",
            "file_name": os.path.basename(file_path),
            "date": datetime.today().strftime("%Y-%m-%d"),
            "parse_error": str(e)
        }

def parse_markdown_by_type(file_path: str, content: str):
    """파일명에 포함된 키워드에 따라 적절한 파서를 호출하는 라우터 함수"""
    if "주간" in os.path.basename(file_path):
        return parse_weekly_markdown_to_json(file_path, content)
    else:
        return parse_daily_markdown_to_json(file_path, content)

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

@app.get("/api/report/detail")
def get_report_detail(
    path: str = Query(..., description="조회할 리포트의 상대 경로 (예: 2026-10/2026-10-08_일간_종합_경제요약.md)"),
    api_key: str = Depends(verify_api_key)
):
    """모바일 앱 용: 검색 결과에서 선택한 특정 원문 리포트 상세 조회"""
    try:
        safe_path = os.path.normpath(path)
        if safe_path.startswith("..") or os.path.isabs(safe_path):
            raise HTTPException(status_code=400, detail="잘못된 경로 접근입니다.")

        file_path = os.path.join(OBSIDIAN_DIR, safe_path)
        
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
    q: str = Query(..., min_length=2, max_length=50, description="검색할 자연어 질문 (최대 50자 제한)"),
    top_k: int = Query(5, ge=1, le=20, description="반환할 최대 결과 개수"),
    api_key: str = Depends(verify_api_key)
):
    """모바일 앱 용: Vector DB 기반 과거 리포트 의미 검색 (Semantic Search)"""
    try:
        safe_q = html.escape(q).replace("'", "").replace('"', "").replace('\n', ' ')
        results = search_similar_reports(query=safe_q, top_k=top_k)
        
        return {
            "status": "ok",
            "query": safe_q,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 처리 중 오류가 발생했습니다: {str(e)}")