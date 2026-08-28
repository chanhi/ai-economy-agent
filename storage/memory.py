import sqlite3
from datetime import datetime
from config import DB_PATH

def init_db():
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute('''
        INSERT OR REPLACE INTO daily_memory (date, keyword, overview, macro_indicators)
        VALUES (?, ?, ?, ?)
    ''', (today_str, keyword, overview, macro_indicators))
    
    conn.commit()
    conn.close()
    print("🧠 [Memory] 오늘의 시장 흐름이 장기 기억소(DB)에 저장되었습니다.")

def get_recent_memory(days=3):
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
    for row in reversed(rows): 
        memory_context += f"- [{row[0]}] 주요 키워드: '{row[1]}' / 데스크 시황: {row[2]}\n"
    return memory_context