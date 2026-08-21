import sqlite3
import os
from datetime import datetime

DB_PATH = "economy_memory.db"

def init_db():
    """DB와 테이블이 없으면 생성합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_memory (
            date TEXT PRIMARY KEY,
            keyword TEXT,
            overview TEXT,
            macro_indicators TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_memory(keyword, overview, macro_indicators):
    """오늘의 분석 결과를 DB에 저장합니다 (같은 날짜면 덮어쓰기)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute('''
        INSERT OR REPLACE INTO daily_memory (date, keyword, overview, macro_indicators)
        VALUES (?, ?, ?, ?)
    ''', (today_str, keyword, overview, macro_indicators))
    
    conn.commit()
    conn.close()
    print(f"🧠 [Memory] 오늘의 시장 흐름이 장기 기억소(DB)에 저장되었습니다.")

def get_recent_memory(days=3):
    """최근 N일간의 시장 흐름을 불러와 LLM 프롬프트용 텍스트로 반환합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, keyword, overview 
        FROM daily_memory 
        ORDER BY date DESC 
        LIMIT ?
    ''', (days,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "최근 저장된 시장 흐름 데이터가 없습니다. 오늘이 첫 분석입니다."
        
    memory_context = ""
    # LLM이 시간 흐름을 이해하기 쉽도록 과거(오래된 날짜)부터 출력되게 순서를 뒤집습니다(reversed).
    for row in reversed(rows): 
        memory_context += f"- [{row[0]}] 주요 키워드: '{row[1]}' / 데스크 시황: {row[2]}\n"
    
    return memory_context