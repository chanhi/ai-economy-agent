import os
import re
import time
import concurrent.futures
from datetime import datetime

from collectors import fetch_domestic_news, fetch_overseas_news, fetch_article_text, fetch_macro_indicators
from memory import init_db, save_memory, get_recent_memory
from notifier import send_discord_alert

# 💡 새로 추가된 Agent E, F를 import 합니다.
from agents import (
    run_desk_agent, run_analyst_agent, run_editor_agent, run_reviewer_agent,
    run_preprocessor_agent, run_memory_synthesizer_agent
)

def chunk_list(data_list, chunk_size):
    for i in range(0, len(data_list), chunk_size):
        yield data_list[i:i + chunk_size]

def main():
    init_db()
    
    broad_search_query = "경제 주식" 
    print("📡 글로벌 경제/주식 뉴스를 대규모로 수집합니다...")
    kr_news = fetch_domestic_news(broad_search_query, count=20)
    us_news = fetch_overseas_news(count=30)
    combined_news = kr_news + us_news
    
    if not combined_news:
        print("⚠️ 수집된 뉴스가 없습니다.")
        return

    macro_indicators = fetch_macro_indicators()

    # Agent A (데스크 - Lite)
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

    # 원문 본문 전문 추출
    print(f"\n🕸️ 선정된 {len(top_full_data)}개 기사의 본문 원문을 추출합니다...")
    for item in top_full_data:
        text = fetch_article_text(item['link'])
        item['full_text'] = text if text else item['description']

    # ==========================================
    # 🧹 [NEW] 전처리 파이프라인 (Agent E - Lite)
    # ==========================================
    print(f"\n✨ Lite 모델을 활용해 {len(top_full_data)}개 기사의 노이즈 제거 및 번역을 시작합니다...")
    # Lite 모델은 분당 15회 호출이 가능하므로 8개를 한 번에 병렬 처리해도 안전합니다.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_item = {executor.submit(run_preprocessor_agent, item): item for item in top_full_data}
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                clean_text = future.result()
                # 원문(full_text)을 깨끗하게 정제된 텍스트로 덮어씌웁니다.
                item['full_text'] = clean_text 
            except Exception as e:
                print(f"❌ 전처리 에러 ({item['title']}): {e}")

    # ==========================================
    # 🧠 [NEW] 기억 합성 파이프라인 (Agent F - Lite)
    # ==========================================
    # 과거 5일 치의 단편적인 기억을 불러옵니다.
    raw_recent_memory = get_recent_memory(days=5)
    # Lite 모델이 이 기억들을 하나의 유려한 '시장 트렌드 맥락'으로 합성해 줍니다.
    synthesized_memory = run_memory_synthesizer_agent(raw_recent_memory)
    print(f"  👉 [합성된 거시 트렌드]: {synthesized_memory[:100]}...\n")


    # Agent B (분석가 - Heavy) : 4개씩 배치 처리 + RPM 쿨타임
    BATCH_SIZE = 4
    analyzed_results = []
    batches = list(chunk_list(top_full_data, BATCH_SIZE))
    
    print(f"\n⚡ [에이전트 B] 정제된 기사를 바탕으로 심층 분석을 시작합니다.")

    for batch_idx, current_batch in enumerate(batches, 1):
        print(f"\n▶️ [배치 {batch_idx}/{len(batches)}] {len(current_batch)}개 기사 병렬 분석 시작...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            # 💡 합성된 트렌드(synthesized_memory)를 Agent B에게 넘겨줍니다!
            futures = [executor.submit(run_analyst_agent, item, synthesized_memory) for item in current_batch]
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    analyzed_results.append(result)
                except Exception as e:
                    print(f"❌ 분석 중 에러 발생: {e}")

        if batch_idx < len(batches):
            print("\n⏳ Heavy 모델 RPM 초기화를 위해 65초간 대기합니다...")
            for remaining in range(65, 0, -10):
                print(f"   남은 시간: {remaining}초...")
                time.sleep(10)
            print("✅ 쿨타임 완료. 다음 배치를 진행합니다.")

    # 데이터 머지
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

    # Agent C (편집장) & Agent D (검수자) 피드백 루프
    print("\n🚀 데이터 취합 완료. Agent C와 Agent D의 자가 수정 루프를 시작합니다...")
    
    MAX_RETRY = 2
    feedback_context = ""
    final_markdown = ""
    
    for attempt in range(MAX_RETRY + 1):
        final_markdown = run_editor_agent(merged_data_for_editor, agent_a_result, macro_indicators, feedback_context)
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
                
    # 파일 저장
    output_dir = "obsidian_notes"
    os.makedirs(output_dir, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    safe_keyword = re.sub(r'[\\/*?:"<>|]', '_', dynamic_keyword)
    filename = os.path.join(output_dir, f"{today_str}_{safe_keyword}_일간_종합_경제요약.md")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(final_markdown)
        
    print(f"\n🎉 [완료] 일간 종합 리포트 생성 완료: {filename}")

    # 메모리 DB 저장
    save_memory(dynamic_keyword, market_overview, macro_indicators)
    
    # 디스코드 알림 전송
    safe_filename = os.path.basename(filename) 
    send_discord_alert(dynamic_keyword, market_overview, macro_indicators, safe_filename)

if __name__ == "__main__":
    main()