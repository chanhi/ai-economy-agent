import glob
import os
import re
from datetime import datetime, timedelta

from config import OBSIDIAN_OUTPUT_DIR
from agents.core import (
    run_theme_extractor_agent,
    run_chief_strategist_agent,
    reset_fallback_count,
    get_fallback_count,
)
from storage.memory import init_db, record_pipeline_run
from storage.vector_db import parse_and_index_markdown, search_similar_reports
from utils.logger import get_logger
# from utils.notifier import send_error_alert

logger = get_logger("weekly_summary")


def main():
    started_at = datetime.now()
    reset_fallback_count()
    init_db()
    logger.info("📅 주간 경제 총결산(RAG 기반) 파이프라인을 시작합니다...")

    try:
        if not os.path.exists(OBSIDIAN_OUTPUT_DIR):
            logger.warning("⚠️ 옵시디언 노트 폴더가 존재하지 않습니다.")
            record_pipeline_run("weekly_summary", started_at, "skipped_no_dir", 0, 0, "폴더 없음")
            return

        today = datetime.now()
        seven_days_ago = today - timedelta(days=7)
        seven_days_ago_str = seven_days_ago.strftime("%Y-%m-%d")

        year_month = today.strftime("%Y-%m")
        target_dir = os.path.join(OBSIDIAN_OUTPUT_DIR, year_month)
        os.makedirs(target_dir, exist_ok=True)

        weekly_outline = ""
        file_count = 0

        # 1. 최근 7일 일간 리포트에서 제목과 Desk 요약 추출
        search_pattern = os.path.join(OBSIDIAN_OUTPUT_DIR, "**", "*_일간_종합_경제요약.md")
        matched_files = sorted(glob.glob(search_pattern, recursive=True))
        for filepath in matched_files:
            filename = os.path.basename(filepath)
            date_str = filename[:10]

            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if seven_days_ago.date() <= file_date.date() <= today.date():
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()

                    summary_match = re.search(
                        r"(> \*\*💡 Desk's Executive Summary:\*\*.*?)(?=\n## )",
                        content,
                        re.DOTALL,
                    )
                    desk_summary = summary_match.group(1).strip() if summary_match else "요약 없음"

                    weekly_outline += f"\n[📅 {date_str} 리포트]\n"
                    weekly_outline += f"- 파일명: {filename}\n"
                    weekly_outline += f"- 핵심 요약:\n{desk_summary}\n"
                    file_count += 1
            except Exception:
                continue

        if file_count == 0:
            logger.warning("⚠️ 지난 1주일간 작성된 일간 리포트가 없어 주간 결산을 생략합니다.")
            record_pipeline_run("weekly_summary", started_at, "skipped_no_reports", 0, 0, "최근 7일 리포트 0건")
            return

        logger.info(f"📚 최근 7일 내 {file_count}개의 리포트 아웃라인 추출 완료.")

        # 2. RAG 기반 핵심 테마 도출 (Agent I)
        themes = run_theme_extractor_agent(weekly_outline)
        logger.info(f"🎯 도출된 핵심 테마: {', '.join(themes)}")

        rag_context = ""
        seen_ids = set()

        for theme in themes:
            results = search_similar_reports(query=theme, top_k=15)
            recent_chunks = []
            for r in results:
                if r["date"] >= seven_days_ago_str and r["id"] not in seen_ids:
                    recent_chunks.append(r)
                    seen_ids.add(r["id"])

            if recent_chunks:
                rag_context += f"\n\n=== 🔎 RAG 검색 테마: {theme} ===\n"
                for r in recent_chunks[:3]:
                    rag_context += f"[{r['date']} | {r['title']}]\n{r['content']}\n"

        # 3. 최종 주간 리포트 집필 (Agent G)
        weekly_markdown = run_chief_strategist_agent(weekly_outline, rag_context)

        week_num = (today.day - 1) // 7 + 1
        safe_filename = f"{year_month}-W{week_num}_주간_경제_총결산.md"
        save_path = os.path.join(target_dir, safe_filename)

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(weekly_markdown)

        # 4. 주간 리포트도 ChromaDB에 인덱싱하여 향후 장기 검색에 활용
        try:
            added_cnt, _ = parse_and_index_markdown(
                filepath=save_path,
                markdown_text=weekly_markdown,
                skip_existing=False,
            )
            logger.info(f"🧠 [Vector DB] 주간 총결산 리포트 {added_cnt}개 테마 청크 인덱싱 완료!")
        except Exception as e:
            logger.warning(f"⚠️ 주간 리포트 벡터 인덱싱 중 경고: {e}")

        record_pipeline_run(
            "weekly_summary",
            started_at,
            "success",
            file_count,
            get_fallback_count(),
            f"테마: {', '.join(themes)[:200]}",
        )
        logger.info(f"\n🎉 [완료] RAG 기반 주간 총결산 리포트 생성 완료: {save_path}")

    except Exception as e:
        logger.error(f"🚨 주간 파이프라인 오류: {e}")
        record_pipeline_run("weekly_summary", started_at, "error", 0, get_fallback_count(), str(e))
        # send_error_alert("weekly_summary", str(e))
        raise


if __name__ == "__main__":
    main()
