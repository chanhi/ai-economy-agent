from fastapi import FastAPI, HTTPException
import sqlite3
from config import DB_PATH

# FastAPI 앱 생성
app = FastAPI(
    title="Economy Agent API",
    description="라즈베리파이 경제 뉴스 AI 에이전트 백엔드 API",
    version="1.0.0"
)

def get_db_connection():
    """SQLite DB 연결 및 Dictionary 형태로 결과 반환 설정"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 컬럼명으로 데이터 접근 가능하게 설정
    return conn

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Economy Agent API Server is running 🚀"}

@app.get("/api/reports/latest")
def get_latest_report():
    """가장 최근에 생성된 일간 거시경제 리포트 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # date 컬럼 기준 내림차순 정렬하여 가장 최신 1개 가져오기
    cursor.execute("SELECT date, keyword, overview, macro_indicators FROM daily_memory ORDER BY date DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="아직 생성된 리포트가 없습니다.")
    return dict(row)

@app.get("/api/queue")
def get_pending_queue():
    """현재 1차 필터링을 통과하여 대기 중인 실시간 기사 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, source, title, description, link, pub_date, collected_at 
        FROM pending_articles 
        ORDER BY collected_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    return {"count": len(rows), "articles": [dict(row) for row in rows]}