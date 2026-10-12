# storage/vector_db.py
import os
import re
import time
import chromadb
from google import genai
from google.genai import types
from config import GEMINI_API_KEY

# 옵시디언 루트 경로 및 ChromaDB 저장 경로
OBSIDIAN_DIR = "/home/chan/economySummary/obsidian_notes"
CHROMA_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")
COLLECTION_NAME = "macro_reports"

EMBEDDING_MODELS = [
    "gemini-embedding-001",
    "models/gemini-embedding-001"
]
ACTIVE_EMBED_MODEL = None

genai_client = genai.Client(api_key=GEMINI_API_KEY)
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)

def get_collection():
    """코사인 유사도(cosine) 기반의 ChromaDB 컬렉션을 반환합니다."""
    return chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

def get_embeddings_batch(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT", max_retries: int = 5) -> list[list[float]]:
    """
    배치 임베딩을 수행하며, 429(TPM/RPM 한도 초과) 발생 시 자동으로 대기 후 재시도합니다.
    """
    global ACTIVE_EMBED_MODEL
    model_name = ACTIVE_EMBED_MODEL or EMBEDDING_MODELS[0]

    for attempt in range(max_retries):
        try:
            response = genai_client.models.embed_content(
                model=model_name,
                contents=texts,
                config=types.EmbedContentConfig(task_type=task_type)
            )
            ACTIVE_EMBED_MODEL = model_name
            return [emb.values for emb in response.embeddings]

        except Exception as e:
            err_msg = str(e)
            # 💡 429 Rate Limit (TPM 30K / RPM 100) 도달 시 자동 대기 후 재시도
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                # 구글이 알려준 retryDelay 초 추출 (없으면 기본 62초 대기)
                delay_match = re.search(r"retry in (\d+(\.\d+)?)s", err_msg)
                wait_sec = int(float(delay_match.group(1))) + 5 if delay_match else 62
                print(f"   ⏳ [429 한도 도달] 분당 토큰/요청 제한 회복을 위해 {wait_sec}초 대기 후 재시도합니다... ({attempt+1}/{max_retries})")
                time.sleep(wait_sec)
                continue
            raise e

    raise RuntimeError("최대 재시도 횟수를 초과하여 임베딩에 실패했습니다.")

def get_embedding(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """단일 텍스트(검색 쿼리 등)를 벡터로 변환합니다."""
    return get_embeddings_batch([text], task_type=task_type)[0]

def parse_and_index_markdown(filepath: str, markdown_text: str = None, skip_existing: bool = True):
    """
    마크다운 리포트를 분할하여 ChromaDB에 적재합니다.
    skip_existing=True일 경우 이미 DB에 저장된 섹션 ID는 API 호출 없이 건너뜁니다.
    반환값: (새로 임베딩된 수, 이미 존재하여 건너뛴 수)
    """
    if markdown_text is None:
        with open(filepath, "r", encoding="utf-8") as f:
            markdown_text = f.read()

    filename = os.path.basename(filepath)
    rel_path = os.path.relpath(filepath, OBSIDIAN_DIR) if filepath.startswith(OBSIDIAN_DIR) else filename
    
    # 1. 날짜, 시장 국면, 키워드 추출
    date_match = re.search(r"date:\s*(\d{4}-\d{2}-\d{2})", markdown_text)
    report_date = date_match.group(1).strip() if date_match else filename[:10]

    phase_match = re.search(r"market_phase:\s*(.+)", markdown_text)
    market_phase = phase_match.group(1).strip() if phase_match else "Unknown"

    title_match = re.search(r"# 🏛️ Daily Macro Report:\s*(.+)", markdown_text)
    report_keyword = title_match.group(1).strip() if title_match else "주요이슈"

    collection = get_collection()
    candidate_chunks = [] # (doc_id, text, metadata) 튜플 리스트

    # 2. 상단 Executive Summary & Deep Dive Summary 추출
    summary_match = re.search(
        r"(> \*\*💡 Desk's Executive Summary:\*\*.*?)(?=\n## )", 
        markdown_text, 
        re.DOTALL
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
                "rel_path": rel_path
            }
        ))

    # 3. 심층 분석 리포트 영역 내 모든 '### ' 기사 섹션 추출 (과거 리포트의 다양한 제목 포맷 완벽 호환)
    deep_dive_section = re.search(
        r"## 📑.*?\n(.*?)(?=\n## 📖|\n## 🔗|\n## 🧭|\Z)", 
        markdown_text, 
        re.DOTALL
    )
    target_body = deep_dive_section.group(1) if deep_dive_section else markdown_text

    article_pattern = re.compile(
        r"###\s+([^\n]+)\n(.*?)(?=\n###\s+|\n## |\Z)", 
        re.DOTALL
    )
    for idx, match in enumerate(article_pattern.finditer(target_body), 1):
        raw_title = match.group(1).strip()
        art_body = match.group(2).strip()
        
        # 포트폴리오 액션 플랜의 하위 헤더(공격투자형/안정투자형)는 기사에서 제외
        if "공격투자형" in raw_title or "안정투자형" in raw_title:
            continue

        # 앞부분의 '1. ', '[1] ' 등 번호 장식 제거하여 깔끔한 제목 추출
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
                "rel_path": rel_path
            }
        ))

    if not candidate_chunks:
        return 0, 0

    # 4. 이미 DB에 적재된 ID인지 확인하여 중복 임베딩(토큰 낭비) 방지
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

    # 새로 추가할 섹션이 있을 때만 Gemini API 호출
    if new_docs:
        embeddings = get_embeddings_batch(new_docs, task_type="RETRIEVAL_DOCUMENT")
        collection.upsert(
            ids=new_ids,
            embeddings=embeddings,
            documents=new_docs,
            metadatas=new_metas
        )

    return len(new_docs), skipped_count

def search_similar_reports(query: str, top_k: int = 5) -> list[dict]:
    """사용자 질문을 벡터로 변환해 가장 유사한 과거 리포트 청크를 반환합니다."""
    collection = get_collection()
    if collection.count() == 0:
        return []

    query_vector = get_embedding(query, task_type="RETRIEVAL_QUERY")
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"]
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
            "content": results["documents"][0][i]
        })

    return formatted_results