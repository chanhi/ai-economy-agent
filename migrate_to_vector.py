# migrate_to_vector.py
import os
import glob
import time
from storage.vector_db import (
    OBSIDIAN_DIR,
    parse_and_index_markdown,
    get_collection,
    search_similar_reports
)

def find_all_daily_reports(target_keyword: str = "일간") -> list[str]:
    """연-월 하위 폴더를 모두 탐색하여 '일간' 리포트 목록을 반환"""
    all_md_files = glob.glob(f"{OBSIDIAN_DIR}/**/*.md", recursive=True)
    daily_files = [
        file_path for file_path in all_md_files
        if target_keyword in os.path.basename(file_path)
    ]
    daily_files.sort(key=os.path.getmtime)
    return daily_files

def run_migration():
    md_files = find_all_daily_reports("일간")
    
    if not md_files:
        print(f"⚠️ '{OBSIDIAN_DIR}' 하위 경로에서 '일간' 마크다운 리포트를 찾지 못했습니다.")
        return False

    print(f"🚀 연-월 폴더 탐색 완료! 총 {len(md_files)}개의 일간 리포트 벡터화를 시작합니다...\n")
    total_added = 0
    total_skipped = 0

    for idx, filepath in enumerate(md_files, 1):
        rel_path = os.path.relpath(filepath, OBSIDIAN_DIR)
        try:
            added, skipped = parse_and_index_markdown(filepath, skip_existing=True)
            total_added += added
            total_skipped += skipped
            
            if added == 0 and skipped > 0:
                print(f"⏭️ [{idx}/{len(md_files)}] '{rel_path}' -> 이미 완료됨 ({skipped}개 섹션 스킵)")
            else:
                print(f"✅ [{idx}/{len(md_files)}] '{rel_path}' -> {added}개 신규 임베딩 완료 (스킵: {skipped}개)")
                # 💡 실제로 API를 호출한 경우에만 TPM(30K) 분산을 위해 4초 대기
                time.sleep(4.0)
                
        except Exception as e:
            print(f"❌ [{idx}/{len(md_files)}] '{rel_path}' 처리 중 오류 발생: {e}")

    collection = get_collection()
    print(f"\n🎉 마이그레이션 완료! (신규 적재: {total_added}개 / 기존 스킵: {total_skipped}개)")
    print(f"📦 현재 ChromaDB 총 저장 청크 수: {collection.count()}개\n")
    return True

def interactive_test():
    print("=" * 65)
    print("🔎 [Vector DB 의미 검색 테스트 모드] (종료하려면 'q' 입력)")
    print("=" * 65)
    
    while True:
        query = input("\n💬 검색할 질문이나 키워드를 입력하세요: ").strip()
        if query.lower() in ['q', 'quit', 'exit']:
            print("테스트를 종료합니다.")
            break
        if not query:
            continue
            
        start_time = time.time()
        results = search_similar_reports(query, top_k=3)
        elapsed = time.time() - start_time
        
        print(f"\n⚡ 검색 소요 시간: {elapsed:.2f}초 (상위 {len(results)}건)")
        print("-" * 65)
        for idx, r in enumerate(results, 1):
            print(f"[{idx}위] 유사도: {r['similarity']}% | 날짜: {r['date']} ({r['market_phase']}) | 경로: {r['rel_path']}")
            print(f"📌 제목: {r['title']}")
            preview = r['content'].replace('\n', ' ')[:150]
            print(f"📄 내용 요약: {preview}...\n")

if __name__ == "__main__":
    if run_migration():
        interactive_test()