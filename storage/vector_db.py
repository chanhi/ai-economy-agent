import os
import re
import time
from datetime import datetime, timedelta

import chromadb
from google import genai
from google.genai import types
from config import CHROMA_DB_DIR, GEMINI_API_KEY, OBSIDIAN_OUTPUT_DIR

# 하위 호환을 위해 OBSIDIAN_DIR 별칭 유지
OBSIDIAN_DIR = OBSIDIAN_OUTPUT_DIR
COLLECTION_NAME = "macro_reports"

EMBEDDING_MODELS = [
    "gemini-embedding-001",
    "models/gemini-embedding-001",
]
ACTIVE_EMBED_MODEL = None

_genai_client = None
_chroma_client = None
_chroma_client_path = None


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return _genai_client


def _get_chroma_client():
    global _chroma_client, _chroma_client_path
    if _chroma_client is None or _chroma_client_path != CHROMA_DB_DIR:
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        _chroma_client_path = CHROMA_DB_DIR
    return _chroma_client


def get_collection():
    """코사인 유사도(cosine) 기반의 ChromaDB 컬렉션을 반환합니다."""
    return _get_chroma_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def get_embeddings_batch(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    max_retries: int = 5,
) -> list[list[float]]:
    """배치 임베딩을 수행하며, 429(TPM/RPM 한도 초과) 발생 시 자동으로 대기 후 재시도합니다."""
    global ACTIVE_EMBED_MODEL
    model_name = ACTIVE_EMBED_MODEL or EMBEDDING_MODELS[0]
    client = _get_genai_client()

    for attempt in range(max_retries):
        try:
            response = client.models.embed_content(
                model=model_name,
                contents=texts,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            ACTIVE_EMBED_MODEL = model_name
            return [emb.values for emb in response.embeddings]

        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                delay_match = re.search(r"retry in (\d+(\.\d+)?)s", err_msg)
                wait_sec = int(float(delay_match.group(1))) + 5 if delay_match else 62
                print(
                    f"   ⏳ [429 한도 도달] 분당 토큰/요청 제한 회복을 위해 {wait_sec}초 대기 후 재시도합니다... "
                    f"({attempt+1}/{max_retries})"
                )
                time.sleep(wait_sec)
                continue
            raise e

    raise RuntimeError("최대 재시도 횟수를 초과하여 임베딩에 실패했습니다.")


def get_embedding(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """단일 텍스트(검색 쿼리 등)를 벡터로 변환합니다."""
    return get_embeddings_batch([text], task_type=task_type)[0]


def _extract_weekly_chunks(markdown_text: str, report_date: str, filename: str, rel_path: str) -> list[tuple]:
    """주간 결산 리포트를 개요 및 핵심 테마별 청크로 분할합니다."""
    chunks = []
    week_id = filename.split("_")[0] if "_" in filename else report_date

    insight_match = re.search(r">\s*\*\*💡 Chief's Insight:\*\*\s*(.+?)(?=\n---|\n## |\Z)", markdown_text, re.DOTALL)
    if insight_match:
        chunks.append((
            f"{week_id}_weekly_overview",
            insight_match.group(1).strip(),
            {
                "date": report_date,
                "keyword": "주간경제총결산",
                "market_phase": "Weekly",
                "title": f"[{week_id}] 주간 총결산 인사이트",
                "type": "weekly_overview",
                "filename": filename,
                "rel_path": rel_path,
            },
        ))

    themes_sec = re.search(r"## 🌊 주간 핵심 테마 내러티브.*?\n(.*?)(?=\n## 📊|\n## 🎯|\n## 🔮|\Z)", markdown_text, re.DOTALL)
    if themes_sec:
        theme_pattern = re.compile(r"###\s+([^\n]+)\n(.*?)(?=\n###\s+|\Z)", re.DOTALL)
        for idx, m in enumerate(theme_pattern.finditer(themes_sec.group(1)), 1):
            clean_title = re.sub(r"^(\[\d+\]|\d+\.)\s*", "", m.group(1).strip()).strip()
            body = m.group(2).strip()
            chunks.append((
                f"{week_id}_weekly_theme_{idx}",
                f"주간 핵심 테마: {clean_title}\n{body}",
                {
                    "date": report_date,
                    "keyword": "주간경제총결산",
                    "market_phase": "Weekly",
                    "title": clean_title,
                    "type": "weekly_theme",
                    "filename": filename,
                    "rel_path": rel_path,
                },
            ))
    return chunks


def parse_and_index_markdown(filepath: str, markdown_text: str = None, skip_existing: bool = True):
    """
    일간 및 주간 마크다운 리포트를 분할하여 ChromaDB에 적재합니다.
    반환값: (새로 임베딩된 수, 이미 존재하여 건너뛴 수)
    """
    if markdown_text is None:
        with open(filepath, "r", encoding="utf-8") as f:
            markdown_text = f.read()

    filename = os.path.basename(filepath)
    abs_filepath = os.path.abspath(filepath)
    abs_obs_dir = os.path.abspath(OBSIDIAN_OUTPUT_DIR)
    rel_path = os.path.relpath(abs_filepath, abs_obs_dir) if abs_filepath.startswith(abs_obs_dir) else filename

    date_match = re.search(r"date:\s*(\d{4}-\d{2}-\d{2})", markdown_text)
    report_date = date_match.group(1).strip() if date_match else filename[:10]

    collection = get_collection()
    candidate_chunks = []

    if "주간" in filename or "Weekly Macro Strategy" in markdown_text:
        candidate_chunks = _extract_weekly_chunks(markdown_text, report_date, filename, rel_path)
    else:
        phase_match = re.search(r"market_phase:\s*(.+)", markdown_text)
        market_phase = phase_match.group(1).strip() if phase_match else "Unknown"

        title_match = re.search(r"# 🏛️ Daily Macro Report:\s*(.+)", markdown_text)
        report_keyword = title_match.group(1).strip() if title_match else "주요이슈"

        summary_match = re.search(
            r"(> \*\*💡 Desk's Executive Summary:\*\*.*?)(?=\n## )",
            markdown_text,
            re.DOTALL,
        )
        if summary_match:
            summary_text = summary_match.group(1).strip()
            candidate_chunks.append((
                f"{report_date}_overview",
                summary_text,
                {
                    "date": report_date,
                    "keyword": report_keyword,
                    "market_phase": market_phase,
                    "title": f"[{report_date}] 종합 시황 브리핑: {report_keyword}",
                    "type": "overview",
                    "filename": filename,
                    "rel_path": rel_path,
                },
            ))

        deep_dive_section = re.search(
            r"## 📑.*?\n(.*?)(?=\n## 📖|\n## 🔗|\n## 🧭|\Z)",
            markdown_text,
            re.DOTALL,
        )
        target_body = deep_dive_section.group(1) if deep_dive_section else markdown_text

        article_pattern = re.compile(
            r"###\s+([^\n]+)\n(.*?)(?=\n###\s+|\n## |\Z)",
            re.DOTALL,
        )
        for idx, match in enumerate(article_pattern.finditer(target_body), 1):
            raw_title = match.group(1).strip()
            art_body = match.group(2).strip()

            if "공격투자형" in raw_title or "안정투자형" in raw_title:
                continue

            clean_title = re.sub(r"^(\[\d+\]|\d+\.)\s*", "", raw_title).strip()
            full_chunk = f"기사 제목: {clean_title}\n{art_body}"
            doc_id = f"{report_date}_art_{idx}"

            candidate_chunks.append((
                doc_id,
                full_chunk,
                {
                    "date": report_date,
                    "keyword": report_keyword,
                    "market_phase": market_phase,
                    "title": clean_title,
                    "type": "article",
                    "filename": filename,
                    "rel_path": rel_path,
                },
            ))

    if not candidate_chunks:
        return 0, 0

    existing_ids = set()
    if skip_existing:
        all_ids = [c[0] for c in candidate_chunks]
        existing_res = collection.get(ids=all_ids, include=[])
        existing_ids = set(existing_res.get("ids", []))

    new_ids, new_docs, new_metas = [], [], []
    for doc_id, doc_text, meta in candidate_chunks:
        if doc_id not in existing_ids:
            new_ids.append(doc_id)
            new_docs.append(doc_text)
            new_metas.append(meta)

    skipped_count = len(existing_ids)

    if new_docs:
        embeddings = get_embeddings_batch(new_docs, task_type="RETRIEVAL_DOCUMENT")
        collection.upsert(
            ids=new_ids,
            embeddings=embeddings,
            documents=new_docs,
            metadatas=new_metas,
        )

    return len(new_docs), skipped_count


def search_similar_reports(query: str, top_k: int = 5) -> list[dict]:
    """사용자 질문을 벡터로 변환해 가장 유사한 과거 리포트 청크를 반환합니다."""
    collection = get_collection()
    total_cnt = collection.count()
    if total_cnt == 0:
        return []

    query_vector = get_embedding(query, task_type="RETRIEVAL_QUERY")
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, total_cnt),
        include=["documents", "metadatas", "distances"],
    )

    formatted_results = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        similarity_score = round((1 - distance) * 100, 1)
        meta = results["metadatas"][0][i]

        formatted_results.append({
            "id": results["ids"][0][i],
            "date": meta.get("date", ""),
            "keyword": meta.get("keyword", ""),
            "market_phase": meta.get("market_phase", "Unknown"),
            "title": meta.get("title", ""),
            "type": meta.get("type", "article"),
            "filename": meta.get("filename", ""),
            "rel_path": meta.get("rel_path", ""),
            "similarity": similarity_score,
            "content": results["documents"][0][i],
        })

    return formatted_results


def search_historical_precedents(query: str, exclude_recent_days: int = 5, top_k: int = 3) -> str:
    """
    일간 파이프라인(Hybrid RAG) 전용:
    최근 단기 기억(exclude_recent_days)과 겹치지 않는 '과거 유사 장세/사건 선례'를 검색해 텍스트로 반환합니다.
    """
    try:
        candidates = search_similar_reports(query=query, top_k=15)
        if not candidates:
            return ""

        cutoff_str = (datetime.now() - timedelta(days=exclude_recent_days)).strftime("%Y-%m-%d")
        precedents = [
            c for c in candidates
            if c.get("date") and c["date"] < cutoff_str and c.get("similarity", 0) >= 55.0
        ][:top_k]

        if not precedents:
            return ""

        lines = []
        for p in precedents:
            snippet = p["content"].strip()[:450]
            lines.append(
                f"- [{p['date']} | 국면:{p['market_phase']} | 유사도:{p['similarity']}%] {p['title']}\n  요약: {snippet}"
            )
        return "\n".join(lines)
    except Exception as e:
        print(f"⚠️ 과거 선례 RAG 검색 스킵: {e}")
        return ""
