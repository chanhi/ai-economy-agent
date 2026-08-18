import os
import time
import concurrent.futures
from datetime import datetime
from collectors import fetch_domestic_news, fetch_overseas_news, fetch_article_text
from agents import run_desk_agent, run_analyst_agent, run_editor_agent

def main():
    # 💡 고정된 키워드를 버리고, 광범위한 경제/주식 뉴스를 끌어모읍니다.
    broad_search_query = "경제 주식" 
    
    print("📡 광범위한 글로벌 경제/주식 뉴스를 수집합니다...")
    # 국내 뉴스를 조금 더 넉넉하게(15개) 가져와서 데스크의 선택지를 넓혀줍니다.
    kr_news = fetch_domestic_news(broad_search_query, count=15)
    us_news = fetch_overseas_news(count=10)
    combined_news = kr_news + us_news
    
    if not combined_news:
        print("⚠️ 수집된 뉴스가 없어 종료합니다.")
        return

    # 2. Agent A (데스크: 키워드 도출 및 3개 선별)
    agent_a_result = run_desk_agent(combined_news)
    
    # 도출된 데이터 분리
    dynamic_keyword = agent_a_result.get('today_keyword', '주요이슈')
    top_3_json = agent_a_result.get('top_news', [])
    
    print(f"\n🎯 [오늘의 시장 키워드]: {dynamic_keyword}")
    
    top_3_full_data = []
    for item in top_3_json:
        original_news = next((n for n in combined_news if n['id'] == item['id']), None)
        if original_news:
            original_news['reason'] = item['reason']
            top_3_full_data.append(original_news)

    # 3. 원문 텍스트 추출
    print("\n🕸️ 선정된 기사의 원문 텍스트를 추출합니다...")
    for item in top_3_full_data:
        text = fetch_article_text(item['link'])
        item['full_text'] = text if text else item['description']

    # 4. Agent B (분석가: 병렬 처리)
    print("\n⚡ [에이전트 B] 3개의 기사를 '동시에' 심층 분석합니다...")
    analyzed_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_analyst_agent, item) for item in top_3_full_data]
        for future in concurrent.futures.as_completed(futures):
            try:
                analyzed_results.append(future.result())
            except Exception as e:
                print(f"❌ 분석 중 에러 발생: {e}")

    # 5. 데이터 병합 및 Safety Sleep
    merged_data_for_editor = []
    for full_item in top_3_full_data:
        b_result = next((res for res in analyzed_results if res['id'] == full_item['id']), None)
        if b_result:
            merged_data_for_editor.append({
                "title": full_item['title'],
                "link": full_item['link'],
                "reason": full_item['reason'],
                "summary": b_result.get('summary', []),
                "terms": b_result.get('terms', [])
            })

    print("\n⏳ API 한도 방어를 위해 5초간 대기합니다...")
    time.sleep(5) 

    # 6. Agent C (편집장) 및 시간대별 파일명 저장
    final_markdown = run_editor_agent(merged_data_for_editor, dynamic_keyword)
    
    output_dir = "obsidian_notes"
    os.makedirs(output_dir, exist_ok=True)
    
    # 💡 파일명 덮어쓰기 방지: YYYY-MM-DD_HHMM 형식 사용 (예: 2026-08-11_0700_금리인하_경제요약.md)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = os.path.join(output_dir, f"{timestamp}_{dynamic_keyword}_경제요약.md")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(final_markdown)
        
    print(f"\n🎉 완료! 리포트 저장됨: {filename}")

if __name__ == "__main__":
    main()