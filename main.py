import os
import re
import time
import concurrent.futures
from datetime import datetime

from collectors import fetch_domestic_news, fetch_overseas_news, fetch_article_text, fetch_macro_indicators
from agents import run_desk_agent, run_analyst_agent, run_editor_agent, run_reviewer_agent
from memory import init_db, save_memory, get_recent_memory
# from notifier import send_discord_alert

def chunk_list(data_list, chunk_size):
    """리스트를 지정한 크기(배치)로 분할하는 헬퍼 함수"""
    for i in range(0, len(data_list), chunk_size):
        yield data_list[i:i + chunk_size]

def main():
    # 1. DB 초기화 (기억 저장소)
    init_db()
    
    # 2. 광범위 뉴스 수집 (국내 25개 + 해외 15개 = 40개)
    broad_search_query = "경제 주식" 
    print("📡 글로벌 경제/주식 뉴스를 대규모로 수집합니다...")
    kr_news = fetch_domestic_news(broad_search_query, count=20)
    us_news = fetch_overseas_news(count=30)
    combined_news = kr_news + us_news
    
    if not combined_news:
        print("⚠️ 수집된 뉴스가 없습니다.")
        return

    macro_indicators = fetch_macro_indicators()

    # 3. Agent A (데스크 - Lite) : 40개 중 핵심 뉴스 8개 선별
    TARGET_ARTICLE_COUNT = 8
    agent_a_result = run_desk_agent(combined_news, target_count=TARGET_ARTICLE_COUNT)
    
    dynamic_keyword = agent_a_result.get('today_keyword', '종합이슈')
    market_overview = agent_a_result.get('market_overview', '')
    top_news_json = agent_a_result.get('top_news', [])
    print(f"\n🎯 [오늘의 시장 키워드]: {dynamic_keyword}")
    
    top_full_data = []
    for item in top_news_json:
        original_news = next((n for n in combined_news if n['id'] == item['id']), None)
        if original_news:
            original_news['reason'] = item['reason']
            top_full_data.append(original_news)

    # 4. 원문 본문 전문 추출
    print(f"\n🕸️ 선정된 {len(top_full_data)}개 기사의 본문 전문을 추출합니다...")
    for item in top_full_data:
        text = fetch_article_text(item['link'])
        item['full_text'] = text if text else item['description']

    recent_memory = get_recent_memory(days=3)

    # 5. Agent B (분석가 - Heavy) : 4개씩 배치 처리 + RPM 방어 65초 쿨타임
    BATCH_SIZE = 4
    analyzed_results = []
    batches = list(chunk_list(top_full_data, BATCH_SIZE))
    
    print(f"\n⚡ [에이전트 B] 총 {len(top_full_data)}개 기사를 {len(batches)}개 배치(각 {BATCH_SIZE}개)로 나누어 분석합니다.")

    for batch_idx, current_batch in enumerate(batches, 1):
        print(f"\n▶️ [배치 {batch_idx}/{len(batches)}] {len(current_batch)}개 기사 병렬 분석 시작...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = [executor.submit(run_analyst_agent, item, recent_memory) for item in current_batch]
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    analyzed_results.append(result)
                except Exception as e:
                    print(f"❌ 분석 중 에러 발생: {e}")

        # 다음 배치가 남아있다면 Heavy 모델 RPM(분당 5회) 제한을 위해 65초 대기
        if batch_idx < len(batches):
            print("\n⏳ Heavy 모델 RPM 초기화를 위해 65초간 대기합니다...")
            for remaining in range(65, 0, -10):
                print(f"   남은 시간: {remaining}초...")
                time.sleep(10)
            print("✅ 쿨타임 완료. 다음 배치를 진행합니다.")

    # 6. 데이터 머지
    merged_data_for_editor = []
    for full_item in top_full_data:
        b_result = next((res for res in analyzed_results if res['id'] == full_item['id']), None)
        if b_result:
            merged_data_for_editor.append({
                "title": full_item['title'],
                "link": full_item['link'],
                "reason": full_item['reason'],
                "summary": b_result.get('summary', []),
                "terms": b_result.get('terms', []),
                "affected_sectors": b_result.get('affected_sectors', [])
            })

    # ==========================================
    # 7. Agent C (편집장) & Agent D (검수자) 피드백 루프
    # ==========================================
    print("\n🚀 데이터 취합 완료. Agent C와 Agent D의 자가 수정(Self-Correction) 루프를 시작합니다...")
    
    MAX_RETRY = 2 # 최대 2번까지만 다시 쓰게 합니다 (무한 루프 방지)
    feedback_context = ""
    final_markdown = ""
    
    for attempt in range(MAX_RETRY + 1):
        # 1) 편집장이 글을 씁니다
        final_markdown = run_editor_agent(merged_data_for_editor, agent_a_result, macro_indicators, feedback_context)
        
        # 2) 검수자가 채점합니다 (Lite 모델)
        review_result = run_reviewer_agent(final_markdown, macro_indicators)
        
        if review_result.get("pass", False):
            print("✅ [검수 통과] 리포트 품질이 기준을 완벽히 충족했습니다!")
            break
        else:
            print(f"⚠️ [검수 반려] 사유: {review_result.get('feedback')}")
            if attempt < MAX_RETRY:
                print("🔄 편집장(Agent C)에게 재작성을 지시합니다...\n")
                feedback_context = review_result.get('feedback')
            else:
                print("🚨 최대 재작성 횟수를 초과했습니다. 현재 버전으로 강제 저장합니다.")
                
    # ==========================================
    # 8. 파일 저장 (특수문자 필터링 적용)
    # ==========================================
    output_dir = "obsidian_notes"
    os.makedirs(output_dir, exist_ok=True)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 💡 파일명에 쓸 수 없는 특수문자(\, /, :, *, ?, ", <, >, |)를 안전하게 언더바(_)로 치환
    safe_keyword = re.sub(r'[\\/*?:"<>|]', '_', dynamic_keyword)
    
    filename = os.path.join(output_dir, f"{today_str}_{safe_keyword}_일간_종합_경제요약.md")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(final_markdown)
        
    print(f"\n🎉 [완료] 일간 종합 리포트 생성 완료: {filename}")

    # 9. 메모리 DB 저장
    save_memory(dynamic_keyword, market_overview, macro_indicators)

    # ==========================================
    # 10. 디스코드 알림 전송
    # ==========================================
    # safe_filename = os.path.basename(filename) 
    # send_discord_alert(dynamic_keyword, market_overview, macro_indicators, safe_filename)

if __name__ == "__main__":
    main()