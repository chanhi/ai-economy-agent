import time
from datetime import datetime
from collectors.news import fetch_domestic_news, fetch_overseas_news
from agents.core import run_hourly_filter_agent
from storage.memory import init_db, save_pending_articles

def main():
    print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 시간당 마이크로 배치 수집 시작")
    init_db()

    # 1. 넉넉한 1차 수집 풀 확보 (총 80개)
    kr_news = fetch_domestic_news("경제 주식", count=15) + fetch_domestic_news("증시 마감", count=15)
    us_news = fetch_overseas_news(count=50) 
    combined_news = kr_news + us_news

    if not combined_news:
        print("⚠️ 수집된 뉴스가 없습니다.")
        return

    print(f"📡 총 {len(combined_news)}개의 뉴스 수집 완료. Lite 모델 기반 1차 필터링을 시작합니다.")

    # 2. Lite 모델 1차 필터링 (최대 15개 통과)
    filter_result = run_hourly_filter_agent(combined_news, target_count=15)
    selected_indices = filter_result.get("selected_indices", [])
    
    selected_articles = []
    for idx in selected_indices:
        if 0 <= idx < len(combined_news):
            selected_articles.append(combined_news[idx])

    # 3. DB 대기열 적재 (UNIQUE 조건에 의해 과거/중복 기사 원천 컷아웃)
    inserted_count = save_pending_articles(selected_articles)
    
    print(f"✅ 필터링된 {len(selected_articles)}개 중, 중복을 제외한 {inserted_count}개의 초신선 기사가 대기열(Queue)에 적재되었습니다.")

if __name__ == "__main__":
    main()