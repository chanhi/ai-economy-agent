from datetime import datetime
from collectors.news import fetch_domestic_news, fetch_overseas_news
from agents.core import run_hourly_filter_agent, reset_fallback_count, get_fallback_count
from storage.memory import init_db, save_pending_articles, record_pipeline_run
from utils.logger import get_logger
from utils.notifier import send_error_alert

logger = get_logger("hourly_collector")


def main():
    started_at = datetime.now()
    reset_fallback_count()
    logger.info(f"\n⏰ [{started_at.strftime('%Y-%m-%d %H:%M:%S')}] 시간당 마이크로 배치 수집 시작")
    init_db()

    try:
        # 1. 국내(30개) + 해외(50개) 수집 후 링크 중복 1차 제거
        kr_raw = fetch_domestic_news("경제 주식", count=15) + fetch_domestic_news("증시 마감", count=15)
        us_raw = fetch_overseas_news(count=50)

        seen_links = set()
        combined_news = []
        for item in kr_raw + us_raw:
            if item["link"] not in seen_links:
                seen_links.add(item["link"])
                combined_news.append(item)

        if not combined_news:
            logger.warning("⚠️ 수집된 뉴스가 없습니다.")
            record_pipeline_run("hourly_collector", started_at, "empty", 0, get_fallback_count(), "수집 기사 0건")
            return

        logger.info(f"📡 중복 제거 후 총 {len(combined_news)}개의 뉴스 수집 완료. Lite 모델 기반 1차 필터링을 시작합니다.")

        # 2. Lite 모델 Structured Output 1차 필터링 (최대 15개 통과)
        filter_result = run_hourly_filter_agent(combined_news, target_count=15)
        selected_indices = filter_result.get("selected_indices", [])

        seen_idx = set()
        selected_articles = []
        for idx in selected_indices:
            if isinstance(idx, int) and 0 <= idx < len(combined_news) and idx not in seen_idx:
                seen_idx.add(idx)
                selected_articles.append(combined_news[idx])

        # 3. DB 대기열 적재 (UNIQUE link 제약으로 과거 중복 기사 차단)
        inserted_count = save_pending_articles(selected_articles)

        logger.info(
            f"✅ 필터링된 {len(selected_articles)}개 중, 신규 {inserted_count}개의 기사가 대기열(Queue)에 적재되었습니다."
        )
        record_pipeline_run(
            "hourly_collector",
            started_at,
            "success",
            inserted_count,
            get_fallback_count(),
            f"후보 {len(combined_news)}건 -> 선별 {len(selected_articles)}건 -> 신규 {inserted_count}건",
        )
    except Exception as e:
        logger.error(f"🚨 시간당 수집 파이프라인 예외 발생: {e}")
        record_pipeline_run("hourly_collector", started_at, "error", 0, get_fallback_count(), str(e))
        send_error_alert("hourly_collector", str(e))
        raise


if __name__ == "__main__":
    main()
