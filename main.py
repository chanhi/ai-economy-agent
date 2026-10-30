import glob
import os
from datetime import datetime

from config import OBSIDIAN_OUTPUT_DIR, REVIEW_MAX_RETRY, TARGET_ARTICLE_COUNT
from storage.memory import (
    init_db,
    save_memory,
    get_recent_memory,
    get_pending_articles,
    clear_pending_articles,
    get_or_set_daily_cache,
    record_pipeline_run,
)
from storage.export import save_markdown_report
from storage.vector_db import parse_and_index_markdown, search_historical_precedents
from collectors.news import fetch_article_text
from collectors.market import (
    fetch_macro_snapshot,
    fetch_major_earnings_schedule,
    fetch_top_movers,
)
from agents.core import (
    run_desk_agent,
    run_analyst_agent,
    run_editor_agent,
    run_reviewer_agent,
    run_preprocessor_agent,
    run_memory_synthesizer_agent,
    run_portfolio_architect_agent,
    reset_fallback_count,
    get_fallback_count,
)
from utils.logger import get_logger
# from utils.notifier import send_discord_alert, send_error_alert

logger = get_logger("daily_pipeline")


def _build_market_extras() -> str:
    """Alpha Vantage 실적 일정 및 주도주를 하루 1회 캐시로 안전하게 조회합니다."""
    blocks = []
    earnings = get_or_set_daily_cache("earnings_schedule", fetch_major_earnings_schedule)
    if earnings and "불가" not in earnings and "못했습니다" not in earnings and "미설정" not in earnings:
        blocks.append(f"### 📅 주요 빅테크 실적 발표 일정 (향후 7일)\n{earnings}")

    movers = get_or_set_daily_cache("top_movers", fetch_top_movers)
    if movers and "불가" not in movers and "못했습니다" not in movers and "미설정" not in movers:
        blocks.append(f"### 🔥 미국 증시 주요 등락/거래 상위 종목\n{movers}")

    return "\n\n".join(blocks)


def main():
    started_at = datetime.now()
    reset_fallback_count()
    logger.info("🚀 일간 거시경제 리포트 파이프라인(고도화 버전 - Hybrid RAG & Deterministic Editor)을 시작합니다...")
    init_db()

    try:
        # 1. 24시간 누적 DB 대기열 조회
        logger.info("\n📦 [1단계] 24시간 동안 누적된 DB 대기열(Queue) 조회 중...")
        pending_news = get_pending_articles(hours=24)

        if len(pending_news) < TARGET_ARTICLE_COUNT:
            msg = f"대기열에 충분한 기사가 없습니다. (현재 {len(pending_news)}개 / 필요 {TARGET_ARTICLE_COUNT}개)"
            logger.warning(f"⚠️ {msg}")
            record_pipeline_run("daily_pipeline", started_at, "skipped_insufficient_queue", len(pending_news), 0, msg)
            # send_error_alert("daily_pipeline (Queue 부족)", msg)
            return

        logger.info(f"✅ 지난 24시간 동안 필터링된 {len(pending_news)}개의 1차 정예 기사를 불러왔습니다.")

        # 2. 실시간 8대 거시 지표(등락률 포함) 수집
        macro_indicators, macro_metrics = fetch_macro_snapshot()
        market_extras = _build_market_extras()

        # 3. Agent A (데스크 - 후보군 13개 선별 + 오늘의 키워드 + 시장 심리 온도 산출)
        target_final_count = TARGET_ARTICLE_COUNT
        agent_a_data = run_desk_agent(
            pending_news,
            target_count=target_final_count + 3,
            macro_indicators=macro_indicators,
        )

        selected_ids = [str(i) for i in agent_a_data.get("selected_ids", [])]
        article_by_id = {str(n["id"]): n for n in pending_news}

        seen_ids = set()
        candidate_articles = []
        for sid in selected_ids:
            if sid in article_by_id and sid not in seen_ids:
                seen_ids.add(sid)
                candidate_articles.append(article_by_id[sid])

        # 만약 LLM이 ID 일부를 누락했더라도 목표 개수를 채울 수 있도록 최신 대기열로 안전 보충
        if len(candidate_articles) < target_final_count:
            for news in pending_news:
                nid = str(news["id"])
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    candidate_articles.append(news)
                if len(candidate_articles) >= target_final_count + 2:
                    break

        if not candidate_articles:
            msg = "데스크 에이전트가 유효한 후보 기사를 선별하지 못했습니다."
            logger.error(f"❌ {msg}")
            record_pipeline_run("daily_pipeline", started_at, "error_empty_selection", 0, get_fallback_count(), msg)
            # send_error_alert("daily_pipeline (데스크 선별 실패)", msg)
            return

        dynamic_keyword = agent_a_data.get("today_keyword", "주요이슈")
        market_overview = agent_a_data.get("market_overview", "")
        sentiment_score = agent_a_data.get("sentiment_score", 50)

        # 4. 단기 기억 합성(Agent F) + 장기 과거 선례 검색(ChromaDB Hybrid RAG)
        past_memory = get_recent_memory(days=5)
        market_context = run_memory_synthesizer_agent(past_memory)
        historical_precedents = search_historical_precedents(
            query=f"{dynamic_keyword} {market_overview}",
            exclude_recent_days=5,
            top_k=3,
        )
        if historical_precedents:
            logger.info("🔎 [Hybrid RAG] ChromaDB에서 과거 유사 장세 선례를 성공적으로 인출했습니다.")

        # 5. 선별 기사 타겟 본문 크롤링(Lazy Crawling) + 전처리(Agent E) + 심층 분석(Agent B)
        merged_data = []
        crawled_cnt = 0
        for article in candidate_articles:
            if len(merged_data) >= target_final_count:
                logger.info(f"✅ 목표한 {target_final_count}개의 심층 분석이 완료되어 분석 루프를 조기 종료합니다.")
                break

            desc = article.get("description", "")
            crawled_body = fetch_article_text(article.get("link", ""))
            if crawled_body:
                crawled_cnt += 1
                article["full_text"] = f"{desc}\n\n{crawled_body}" if desc else crawled_body
            else:
                article["full_text"] = desc

            clean_text = run_preprocessor_agent(article)
            article["full_text"] = clean_text

            analysis = run_analyst_agent(article, market_context, historical_precedents)
            if not analysis or not analysis.get("summary"):
                continue

            analysis["title"] = article.get("title", "")
            analysis["link"] = article.get("link", "")
            analysis["reason"] = analysis.get("selection_reason", "")
            merged_data.append(analysis)

        if not merged_data:
            msg = "개별 기사 심층 분석(Agent B) 결과가 비어 있어 리포트 생성을 중단합니다."
            logger.error(f"❌ {msg}")
            record_pipeline_run("daily_pipeline", started_at, "error_empty_analysis", 0, get_fallback_count(), msg)
            # send_error_alert("daily_pipeline (분석 결과 없음)", msg)
            return

        # 6. 하이브리드 조판(Agent C) & 무결성 검수(Agent D) 루프
        final_markdown = ""
        feedback = ""
        for attempt in range(REVIEW_MAX_RETRY + 1):
            if attempt > 0:
                logger.info(f"\n🔄 [루프] 피드백을 반영하여 {attempt}번째 재작성 중...")

            final_markdown = run_editor_agent(
                merged_data=merged_data,
                agent_a_data=agent_a_data,
                macro_indicators=macro_indicators,
                feedback=feedback,
                historical_precedents=historical_precedents,
                market_extras=market_extras,
            )
            review_result = run_reviewer_agent(final_markdown, macro_indicators)

            if review_result.get("pass"):
                logger.info("\n✅ 검수 통과! 리포트 작성을 확정합니다.")
                break
            else:
                feedback = review_result.get("feedback", "양식 오류 및 지표 누락이 발견되었습니다.")
                logger.warning(f"\n❌ 검수 반려됨: {feedback}")
                if attempt == REVIEW_MAX_RETRY:
                    logger.warning("🚨 최대 재작성 횟수를 초과했습니다. 현재 본문으로 진행합니다.")

        # 7. 포트폴리오 설계사(Agent H) 액션 플랜 추가
        portfolio_strategy = run_portfolio_architect_agent(final_markdown)
        if portfolio_strategy and portfolio_strategy.strip() != "{}":
            final_markdown += f"\n\n{portfolio_strategy.strip()}"

        # 8. 파일 저장, 장기 기억(정량 지표 포함) 저장 및 Vector DB 적재
        saved_filepath = save_markdown_report(dynamic_keyword, final_markdown)
        save_memory(
            keyword=dynamic_keyword,
            overview=market_overview,
            macro_indicators=macro_indicators,
            metrics_dict=macro_metrics,
            sentiment_score=sentiment_score,
        )
        # send_discord_alert(dynamic_keyword, market_overview, macro_indicators, saved_filepath)

        try:
            target_path = saved_filepath
            if not target_path or not isinstance(target_path, str) or not os.path.exists(target_path):
                md_files = [
                    f for f in glob.glob(f"{OBSIDIAN_OUTPUT_DIR}/**/*.md", recursive=True)
                    if "일간" in os.path.basename(f)
                ]
                target_path = max(md_files, key=os.path.getmtime) if md_files else "today_report.md"

            added_cnt, _ = parse_and_index_markdown(
                filepath=target_path,
                markdown_text=final_markdown,
                skip_existing=False,
            )
            logger.info(f"🧠 [Vector DB] 오늘자 리포트 {added_cnt}개 섹션 벡터 임베딩 및 적재 완료!")
        except Exception as e:
            logger.warning(f"⚠️ [Vector DB 인덱싱 에러] 리포트 저장은 성공했으나 벡터 적재 중 오류 발생: {e}")

        # 9. 처리 완료된 대기열 초기화 및 실행 메트릭 기록
        clear_pending_articles()
        record_pipeline_run(
            "daily_pipeline",
            started_at,
            "success",
            len(merged_data),
            get_fallback_count(),
            f"키워드:{dynamic_keyword} | 본문크롤링:{crawled_cnt}/{len(merged_data)} | 투심:{sentiment_score}",
        )
        logger.info("🎉 모든 파이프라인이 성공적으로 종료되었습니다!")

    except Exception as e:
        logger.error(f"🚨 일간 파이프라인 치명적 오류: {e}")
        record_pipeline_run("daily_pipeline", started_at, "error", 0, get_fallback_count(), str(e))
        # send_error_alert("daily_pipeline", str(e))
        raise


if __name__ == "__main__":
    main()
