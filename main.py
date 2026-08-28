import time
import concurrent.futures

from config import TARGET_ARTICLE_COUNT, PREPROCESSOR_WORKERS, HEAVY_MODEL_COOLDOWN, REVIEW_MAX_RETRY
from collectors.news import fetch_domestic_news, fetch_overseas_news, fetch_article_text
from collectors.market import fetch_macro_indicators, fetch_major_earnings_schedule, fetch_top_movers
from agents.core import (
    run_desk_agent, run_analyst_agent, run_editor_agent, run_reviewer_agent,
    run_preprocessor_agent, run_memory_synthesizer_agent
)
from storage.memory import init_db, save_memory, get_recent_memory
from storage.export import save_markdown_report
# from utils.notifier import send_discord_alert

def main():
    # 1. 초기화 및 수집부
    init_db()
    print("📡 글로벌 경제/주식 뉴스를 대규모로 수집합니다...")
    kr_news = fetch_domestic_news("경제 주식", count=10) + fetch_domestic_news("증시 마감 시황 일정", count=10)
    combined_news = kr_news + fetch_overseas_news(count=30)
    
    if not combined_news:
        print("⚠️ 수집된 뉴스가 없습니다.")
        return

    macro_indicators = fetch_macro_indicators()
    macro_indicators += f"\n\n[이번 주 주요 빅테크 실적 일정]\n{fetch_major_earnings_schedule()}"
    macro_indicators += f"\n\n[미국 증시 일일 주도주 (Top Movers)]\n{fetch_top_movers()}"

    # 2. Agent A (데스크 큐레이션)
    agent_a_result = run_desk_agent(combined_news, target_count=TARGET_ARTICLE_COUNT)
    dynamic_keyword = agent_a_result.get('today_keyword', '종합이슈')
    market_overview = agent_a_result.get('market_overview', '')
    print(f"\n🎯 [오늘의 시장 키워드]: {dynamic_keyword}")
    
    top_full_data = [
        {**next((n for n in combined_news if n['id'] == item['id']), {}), 'reason': item['reason']}
        for item in agent_a_result.get('top_news', []) if next((n for n in combined_news if n['id'] == item['id']), None)
    ]

    print(f"\n🕸️ 선정된 {len(top_full_data)}개 기사의 본문 원문을 추출합니다...")
    for item in top_full_data:
        text = fetch_article_text(item.get('link', ''))
        item['full_text'] = text if text else item.get('description', '')

    # 3. Agent E (본문 정제 - 병렬)
    print(f"\n✨ Lite 모델을 활용해 {len(top_full_data)}개 기사의 노이즈 제거 및 번역을 시작합니다...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=PREPROCESSOR_WORKERS) as executor:
        futures = {executor.submit(run_preprocessor_agent, item): item for item in top_full_data}
        for future in concurrent.futures.as_completed(futures):
            try:
                futures[future]['full_text'] = future.result()
            except Exception as e:
                print(f"❌ 전처리 에러 ({futures[future].get('title')}): {e}")

    # 4. Agent F (과거 기억 합성)
    synthesized_memory = run_memory_synthesizer_agent(get_recent_memory(days=5))
    print(f"  👉 [합성된 거시 트렌드]: {synthesized_memory[:100]}...\n")

    # 5. Agent B (심층 분석 - 순차 처리)
    analyzed_results = []
    print(f"\n⚡ [에이전트 B] 정제된 기사 {len(top_full_data)}건의 순차 심층 분석을 시작합니다.")
    for idx, item in enumerate(top_full_data, 1):
        print(f"\n▶️ [{idx}/{len(top_full_data)}] '{item.get('title', '')[:20]}...' 분석 중...")
        try:
            analyzed_results.append(run_analyst_agent(item, synthesized_memory))
            if idx < len(top_full_data):
                print(f"⏳ 과부하 방지를 위해 {HEAVY_MODEL_COOLDOWN}초 대기합니다...")
                time.sleep(HEAVY_MODEL_COOLDOWN)
        except Exception as e:
            print(f"❌ 분석 중 에러 발생: {e}")

    # 6. 데이터 병합
    merged_data_for_editor = []
    for full_item in top_full_data:
        b_result = next((res for res in analyzed_results if res['id'] == full_item['id']), None)
        if b_result:
            merged_data_for_editor.append({
                "title": full_item['title'], "link": full_item['link'], "reason": full_item['reason'],
                "summary": b_result.get('summary', []), "terms": b_result.get('terms', []),
                "affected_sectors": b_result.get('affected_sectors', [])
            })

    # 7. Agent C & D (편집장 및 검수 루프)
    print("\n🚀 데이터 취합 완료. 자가 수정 루프를 시작합니다...")
    feedback_context = ""
    final_markdown = ""
    for attempt in range(REVIEW_MAX_RETRY + 1):
        final_markdown = run_editor_agent(merged_data_for_editor, agent_a_result, macro_indicators, feedback_context)
        review_result = run_reviewer_agent(final_markdown, macro_indicators)
        
        if review_result.get("pass", False):
            print("✅ [검수 통과] 리포트 품질이 기준을 완벽히 충족했습니다!")
            break
        else:
            print(f"⚠️ [검수 반려] 사유: {review_result.get('feedback')}")
            if attempt < REVIEW_MAX_RETRY:
                print("🔄 편집장에게 재작성을 지시합니다...\n")
                feedback_context = review_result.get('feedback')
            else:
                print("🚨 최대 재작성 횟수를 초과했습니다. 강제 저장합니다.")

    # 8. 파일 저장 및 알림 (분리된 Storage & Utils 활용)
    saved_filepath = save_markdown_report(dynamic_keyword, final_markdown)
    save_memory(dynamic_keyword, market_overview, macro_indicators)
    # send_discord_alert(dynamic_keyword, market_overview, macro_indicators, saved_filepath)

if __name__ == "__main__":
    main()