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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_articles (
            id TEXT,
            source TEXT,
            title TEXT,
            description TEXT,
            link TEXT UNIQUE,
            pub_date TEXT,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_pending_articles(articles):
    """1차 필터링을 통과한 기사들을 대기열에 넣습니다. 중복 기사는 자동 무시됩니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted_count = 0
    
    for item in articles:
        try:
            # INSERT OR IGNORE: 이미 존재하는 link면 에러 없이 무시 (과거/중복 기사 차단)
            cursor.execute('''
                INSERT OR IGNORE INTO pending_articles (id, source, title, description, link, pub_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (item['id'], item['source'], item['title'], item['description'], item['link'], str(item.get('pub_date', ''))))
            
            if cursor.rowcount > 0:
                inserted_count += 1
        except Exception as e:
            print(f"❌ DB 저장 에러 ({item['title'][:10]}): {e}")
            
    conn.commit()
    conn.close()
    return inserted_count

def get_pending_articles(hours=24):
    """최근 지정된 시간 내에 적재된 대기열 기사들을 모두 가져옵니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # SQLite datetime 함수를 이용해 24시간 이내 데이터만 추출
    cursor.execute('''
        SELECT id, source, title, description, link, pub_date 
        FROM pending_articles 
        WHERE datetime(collected_at) >= datetime('now', ?)
    ''', (f'-{hours} hours',))
    
    rows = cursor.fetchall()
    conn.close()
    
    articles = []
    for row in rows:
        articles.append({
            "id": row[0],
            "source": row[1],
            "title": row[2],
            "description": row[3],
            "link": row[4],
            "pub_date": row[5]
        })
    return articles

def clear_pending_articles():
    """일간 리포트 생성이 완료되면 대기열을 완전히 비워 다음 날을 준비합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM pending_articles')
    conn.commit()
    conn.close()
    print("🧹 [정리] 처리가 완료된 DB 대기열을 비웠습니다.")

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