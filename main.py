import time
from datetime import datetime

from config import TARGET_ARTICLE_COUNT
from storage.memory import init_db, save_memory, get_recent_memory, get_pending_articles, clear_pending_articles
from storage.export import save_markdown_report
from utils.notifier import send_discord_alert
from collectors.market import fetch_macro_indicators
from agents.core import (
    run_desk_agent, run_analyst_agent, run_editor_agent, run_reviewer_agent,
    run_preprocessor_agent, run_memory_synthesizer_agent, run_portfolio_architect_agent
)

def main():
    print("🚀 일간 거시경제 리포트 파이프라인(Phase 1 - Queue 기반)을 시작합니다...")
    init_db()

    # 💡 1. 실시간 수집 대신 DB 대기열(Queue)에서 기사 호출
    print("\n📦 [1단계] 24시간 동안 누적된 DB 대기열(Queue) 조회 중...")
    pending_news = get_pending_articles(hours=24)
    
    if len(pending_news) < TARGET_ARTICLE_COUNT:
        print(f"⚠️ 대기열에 충분한 기사가 없습니다. (현재 {len(pending_news)}개 / 필요 {TARGET_ARTICLE_COUNT}개)")
        print("시간당 수집(hourly_collector.py)이 충분히 누적된 후 다시 실행해주세요.")
        return

    print(f"✅ 지난 24시간 동안 필터링된 {len(pending_news)}개의 1차 정예 기사를 불러왔습니다.")

    # 2. Agent A (데스크 - 최종 10개 선별)
    agent_a_data, selected_indices = run_desk_agent(pending_news, count=TARGET_ARTICLE_COUNT)
    
    selected_articles = []
    for idx in selected_indices:
        if 0 <= idx < len(pending_news):
            selected_articles.append(pending_news[idx])
            
    if not selected_articles:
         print("❌ 데스크 에이전트가 기사를 선별하지 못했습니다.")
         return

    # 3. Agent E (병렬 전처리 - 노이즈 제거 및 번역)
    preprocessed_articles = run_preprocessor_agent(selected_articles)

    # 4. 거시 지표 수집 및 Agent F (기억 합성)
    macro_indicators = fetch_macro_indicators()
    past_memory = get_recent_memory(days=5)
    market_context = run_memory_synthesizer_agent(past_memory)

    # 5. Agent B (순차 딥다이브 분석 - 429 에러 방어)
    merged_data = run_analyst_agent(preprocessed_articles, market_context)

    # 6. Agent C (편집장) & Agent D (검수자) 자가 수정 루프
    max_retries = 2
    final_markdown = ""
    feedback = ""
    
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n🔄 [루프] 피드백을 반영하여 {attempt}번째 재작성 중...")
            
        final_markdown = run_editor_agent(merged_data, agent_a_data, macro_indicators, feedback)
        review_result = run_reviewer_agent(final_markdown)
        
        if review_result.get("pass"):
            print("\n✅ 검수 통과! 리포트 작성을 확정합니다.")
            break
        else:
            feedback = review_result.get("feedback", "양식 오류 및 지표 누락이 발견되었습니다. 전면 재작성 요망.")
            print(f"\n❌ 검수 반려됨: {feedback}")
            if attempt == max_retries:
                print("🚨 최대 재작성 횟수를 초과했습니다. 강제 진행합니다.")

    # 7. Agent H (포트폴리오 설계사) 액션 플랜 추가
    portfolio_strategy = run_portfolio_architect_agent(final_markdown)
    final_markdown += f"\n\n{portfolio_strategy}"

    # 8. 저장, 알림 및 큐(Queue) 초기화
    dynamic_keyword = agent_a_data.get('today_keyword', '주요이슈')
    market_overview = agent_a_data.get('market_overview', '')
    
    saved_filepath = save_markdown_report(dynamic_keyword, final_markdown)
    save_memory(dynamic_keyword, market_overview, macro_indicators)
    send_discord_alert(dynamic_keyword, market_overview, macro_indicators, saved_filepath)
    
    # 💡 9. 처리가 끝난 큐를 싹 비워서 다음 날 찌꺼기가 남지 않게 방지
    clear_pending_articles()
    
    print("🎉 모든 파이프라인이 성공적으로 종료되었습니다!")

if __name__ == "__main__":
    main()