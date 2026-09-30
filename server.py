import glob
import os
import re
from datetime import datetime
from config import API_KEY_NAME, SECRET_API_KEY
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader

# 옵시디언 마크다운 리포트 저장 절대 경로
OBSIDIAN_DIR = "/home/chan/economySummary/obsidian_notes"

# FastAPI 앱 생성
app = FastAPI(
    title="Economy Agent API",
    description="모바일 앱 연동을 위한 거시경제 리포트 전용 API",
    version="1.1.0"
)

# 💡 1. API 키 설정 (클라이언트가 헤더에 'X-API-Key'라는 이름으로 보내야 함)
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
        
        # 💡 본문이 아닌 '파일 이름'에 타겟 키워드가 명확히 들어있는지 확인
        if target_keyword in file_name:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return file_path, content
                
    return None, None

def parse_markdown_to_json(file_path: str, content: str):
    """마크다운 본문을 모바일 앱 UI 위젯 단위로 파싱"""
    try:
        # Frontmatter 메타데이터 파싱
        date_match = re.search(r"date:\s*(.+)", content)
        market_phase_match = re.search(r"market_phase:\s*(.+)", content)
        
        # 핵심 요약 추출 (옵션)
        desk_summary_match = re.search(r">\s*\*\*💡 Desk's Executive Summary:\*\*\s*(.+)", content)
        editor_insight_match = re.search(r">\s*\*\*🎯 Editor's Insight:\*\*\s*(.+)", content)
        
        # 섹션별 추출
        macro_section = re.search(r"## 📊 글로벌 매크로 지표 브리핑\n(.*?)(?=## 📑|## 📖|## 🔗|$)", content, re.DOTALL)
        macro_text = macro_section.group(1).strip() if macro_section else ""
        
        news_section = re.search(r"## 📑 심층 분석 리포트.*?\n(.*?)(?=## 📖|## 🔗|$)", content, re.DOTALL)
        news_text = news_section.group(1).strip() if news_section else ""

        terms_section = re.search(r"## 📖 오늘의 금융/경제 단어장\n(.*?)(?=## 🔗|$)", content, re.DOTALL)
        terms_text = terms_section.group(1).strip() if terms_section else ""

        return {
            "file_name": os.path.basename(file_path),
            "date": date_match.group(1).strip() if date_match else datetime.today().strftime("%Y-%m-%d"),
            "market_phase": market_phase_match.group(1).strip() if market_phase_match else "Unknown",
            "insights": {
                "desk_summary": desk_summary_match.group(1).strip() if desk_summary_match else "",
                "editor_insight": editor_insight_match.group(1).strip() if editor_insight_match else ""
            },
            "macro_indicators": macro_text,
            "news_analysis": news_text,
            "terms": terms_text,
            "full_markdown": content  # 통짜 렌더링용
        }
    except Exception as e:
        return {
            "file_name": os.path.basename(file_path),
            "date": datetime.today().strftime("%Y-%m-%d"),
            "parse_error": str(e),
            "full_markdown": content
        }

@app.get("/api/report/today")
def get_daily_report(api_key: str = Depends(verify_api_key)):
    """모바일 앱 용: 가장 최신 일간 거시경제 리포트 조회"""
    # 💡 파일명에 '일간'이 포함된 가장 최신 파일 검색
    file_path, content = find_latest_markdown("일간")
    
    if not file_path:
        raise HTTPException(status_code=404, detail="일간 리포트를 찾을 수 없습니다.")
        
    return parse_markdown_to_json(file_path, content)

@app.get("/api/report/weekly")
def get_weekly_report(api_key: str = Depends(verify_api_key)):
    """모바일 앱 용: 가장 최신 주간 결산 리포트 조회"""
    # 💡 파일명에 '주간'이 포함된 가장 최신 파일 검색
    file_path, content = find_latest_markdown("주간")
    
    if not file_path:
        raise HTTPException(status_code=404, detail="주간 리포트를 찾을 수 없습니다.")
        
    return parse_markdown_to_json(file_path, content)