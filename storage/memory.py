import json
import re
import sqlite3
from datetime import datetime
from config import DB_PATH


def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, col_type: str):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_memory (
            date TEXT PRIMARY KEY,
            keyword TEXT,
            overview TEXT,
            macro_indicators TEXT,
            metrics_json TEXT,
            sentiment_score INTEGER
        )
    ''')
    # 기존 운영 DB와의 무중단 하위 호환 마이그레이션
    _ensure_column(cursor, "daily_memory", "metrics_json", "TEXT")
    _ensure_column(cursor, "daily_memory", "sentiment_score", "INTEGER")

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_cache (
            cache_date TEXT,
            cache_key TEXT,
            content TEXT,
            PRIMARY KEY (cache_date, cache_key)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_name TEXT,
            started_at TEXT,
            finished_at TEXT,
            duration_sec REAL,
            status TEXT,
            articles_processed INTEGER DEFAULT 0,
            fallback_count INTEGER DEFAULT 0,
            notes TEXT
        )
    ''')

    conn.commit()
    conn.close()


def save_pending_articles(articles: list[dict]) -> int:
    """1차 필터링을 통과한 기사들을 대기열에 넣습니다. 중복 링크는 자동 무시됩니다."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted_count = 0

    for item in articles:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO pending_articles (id, source, title, description, link, pub_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                item["id"],
                item["source"],
                item["title"],
                item["description"],
                item["link"],
                str(item.get("pub_date", "")),
            ))
            if cursor.rowcount > 0:
                inserted_count += 1
        except Exception as e:
            print(f"❌ DB 저장 에러 ({item.get('title', '')[:10]}): {e}")

    conn.commit()
    conn.close()
    return inserted_count


def get_pending_articles(hours: int = 24) -> list[dict]:
    """최근 지정된 시간 내에 적재된 대기열 기사들을 가져옵니다. 레거시 중복 ID 방어를 위해 rowid 폴백을 보강합니다."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT rowid, id, source, title, description, link, pub_date
        FROM pending_articles
        WHERE datetime(collected_at) >= datetime('now', ?)
        ORDER BY rowid ASC
    ''', (f"-{hours} hours",))

    rows = cursor.fetchall()
    conn.close()

    seen_ids = set()
    articles = []
    for rowid, aid, source, title, desc, link, pub_date in rows:
        # 기존 DB에 남아있던 순번 ID(KR_1 등) 충돌 시에도 고유 식별이 가능하도록 보정
        unique_id = str(aid) if (aid and str(aid) not in seen_ids) else f"{aid}_{rowid}"
        seen_ids.add(unique_id)
        articles.append({
            "id": unique_id,
            "source": source,
            "title": title,
            "description": desc,
            "link": link,
            "pub_date": pub_date,
        })
    return articles


def clear_pending_articles():
    """일간 리포트 생성이 완료되면 대기열을 완전히 비워 다음 날을 준비합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_articles")
    conn.commit()
    conn.close()
    print("🧹 [정리] 처리가 완료된 DB 대기열을 비웠습니다.")


def save_memory(
    keyword: str,
    overview: str,
    macro_indicators: str,
    metrics_dict: dict | None = None,
    sentiment_score: int | None = None,
):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    metrics_json = json.dumps(metrics_dict, ensure_ascii=False) if metrics_dict else None

    cursor.execute('''
        INSERT OR REPLACE INTO daily_memory (date, keyword, overview, macro_indicators, metrics_json, sentiment_score)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (today_str, keyword, overview, macro_indicators, metrics_json, sentiment_score))

    conn.commit()
    conn.close()
    print("🧠 [Memory] 오늘의 시장 흐름과 정량 지표가 장기 기억소(DB)에 저장되었습니다.")


def get_recent_memory(days: int = 5) -> str:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, keyword, overview, sentiment_score
        FROM daily_memory
        ORDER BY date DESC
        LIMIT ?
    ''', (days,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "최근 저장된 시장 흐름 데이터가 없습니다. 오늘이 첫 분석입니다."

    memory_context = ""
    for date_str, keyword, overview, sentiment in reversed(rows):
        sent_tag = f" (투심 {sentiment}점)" if sentiment is not None else ""
        memory_context += f"- [{date_str}] 주요 키워드: '{keyword}'{sent_tag} / 데스크 시황: {overview}\n"
    return memory_context


def _parse_legacy_macro_string(macro_str: str) -> dict:
    """기존 문자열 포맷('S&P 500: 7,720.39 | 원/달러 환율: 1,339.48원 ...')에서 수치 시계열을 복원합니다."""
    parsed = {}
    if not macro_str:
        return parsed
    for part in macro_str.split("|"):
        part = part.strip()
        m = re.match(r"^([^:]+):\s*\$?([0-9,]+(?:\.[0-9]+)?)", part)
        if m:
            key = m.group(1).strip()
            try:
                val = float(m.group(2).replace(",", ""))
                parsed[key] = {"value": val, "display": part.split(":", 1)[1].strip()}
            except ValueError:
                continue
    return parsed


def get_macro_history(days: int = 30) -> list[dict]:
    """모바일 앱 차트 렌더링을 위한 최근 N일 시계열 매크로 및 투심 데이터를 반환합니다."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, keyword, macro_indicators, metrics_json, sentiment_score
        FROM daily_memory
        ORDER BY date DESC
        LIMIT ?
    ''', (days,))
    rows = cursor.fetchall()
    conn.close()

    history = []
    for date_str, keyword, macro_str, metrics_json, sentiment_score in reversed(rows):
        metrics = {}
        if metrics_json:
            try:
                metrics = json.loads(metrics_json)
            except Exception:
                metrics = {}
        if not metrics and macro_str:
            metrics = _parse_legacy_macro_string(macro_str)

        history.append({
            "date": date_str,
            "keyword": keyword,
            "sentiment_score": sentiment_score,
            "metrics": metrics,
            "raw_summary": macro_str or "",
        })
    return history


def get_or_set_daily_cache(cache_key: str, fetcher_fn) -> str:
    """Alpha Vantage 등 일일 호출 제한이 엄격한 외부 API 결과를 당일 SQLite에 캐싱합니다."""
    init_db()
    today_str = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content FROM market_cache WHERE cache_date = ? AND cache_key = ?",
        (today_str, cache_key),
    )
    row = cursor.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]

    content = fetcher_fn()
    if content and "한도 초과" not in content and "불러오지 못했습니다" not in content:
        cursor.execute(
            "INSERT OR REPLACE INTO market_cache (cache_date, cache_key, content) VALUES (?, ?, ?)",
            (today_str, cache_key, content),
        )
        conn.commit()
    conn.close()
    return content


def record_pipeline_run(
    pipeline_name: str,
    started_at: datetime,
    status: str,
    articles_processed: int = 0,
    fallback_count: int = 0,
    notes: str = "",
):
    init_db()
    finished_at = datetime.now()
    duration = round((finished_at - started_at).total_seconds(), 2)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO pipeline_runs
        (pipeline_name, started_at, finished_at, duration_sec, status, articles_processed, fallback_count, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        pipeline_name,
        started_at.strftime("%Y-%m-%d %H:%M:%S"),
        finished_at.strftime("%Y-%m-%d %H:%M:%S"),
        duration,
        status,
        articles_processed,
        fallback_count,
        notes[:500],
    ))
    conn.commit()
    conn.close()


def get_recent_pipeline_runs(limit: int = 5) -> list[dict]:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pipeline_name, started_at, finished_at, duration_sec, status, articles_processed, fallback_count, notes
        FROM pipeline_runs
        ORDER BY id DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "pipeline_name": r[0],
            "started_at": r[1],
            "finished_at": r[2],
            "duration_sec": r[3],
            "status": r[4],
            "articles_processed": r[5],
            "fallback_count": r[6],
            "notes": r[7],
        }
        for r in rows
    ]
