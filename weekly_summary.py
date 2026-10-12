import os
import glob
import re
from datetime import datetime, timedelta
from config import OBSIDIAN_OUTPUT_DIR
from agents.core import run_theme_extractor_agent, run_chief_strategist_agent 
from storage.vector_db import search_similar_reports

def main():
    print("📅 주간 경제 총결산(RAG 기반) 파이프라인을 시작합니다...")
    
    if not os.path.exists(OBSIDIAN_OUTPUT_DIR):
        print("⚠️ 옵시디언 노트 폴더가 존재하지 않습니다.")
        return

    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    seven_days_ago_str = seven_days_ago.strftime("%Y-%m-%d")
    
    year_month = today.strftime("%Y-%m")
    target_dir = os.path.join(OBSIDIAN_OUTPUT_DIR, year_month)
    os.makedirs(target_dir, exist_ok=True)
    
    weekly_outline = ""
    file_count = 0
    
    # 💡 1. 일간 리포트 파일에서 '제목'과 'Desk 요약'만 추출하여 가벼운 Outline 생성
    search_pattern = os.path.join(OBSIDIAN_OUTPUT_DIR, "**", "*_일간_종합_경제요약.md")
    for filepath in glob.glob(search_pattern, recursive=True):
        filename = os.path.basename(filepath)
        date_str = filename[:10] 
        
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if seven_days_ago <= file_date <= today:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                summary_match = re.search(r"(> \*\*💡 Desk's Executive Summary:\*\*.*?)(?=\n## )", content, re.DOTALL)
                desk_summary = summary_match.group(1).strip() if summary_match else "요약 없음"
                
                weekly_outline += f"\n[📅 {date_str} 리포트]\n"
                weekly_outline += f"- 파일명: {filename}\n"
                weekly_outline += f"- 핵심 요약:\n{desk_summary}\n"
                
                file_count += 1
        except Exception as e:
            continue

    if file_count == 0:
        print("⚠️ 지난 1주일간 작성된 일간 리포트가 없어 주간 결산을 생략합니다.")
        return

    print(f"📚 최근 7일 내 {file_count}개의 리포트 아웃라인 추출 완료.")

    # 💡 2. RAG 기반 핵심 테마 검색 (Agent I 활용)
    themes = run_theme_extractor_agent(weekly_outline)
    print(f"🎯 도출된 핵심 테마: {', '.join(themes)}")
    
    rag_context = ""
    seen_ids = set()
    
    for theme in themes:
        results = search_similar_reports(query=theme, top_k=15)
        
        recent_chunks = []
        for r in results:
            if r['date'] >= seven_days_ago_str and r['id'] not in seen_ids:
                recent_chunks.append(r)
                seen_ids.add(r['id'])
        
        if recent_chunks:
            rag_context += f"\n\n=== 🔎 RAG 검색 테마: {theme} ===\n"
            for r in recent_chunks[:3]:
                rag_context += f"[{r['date']} | {r['title']}]\n{r['content']}\n"

    # 💡 3. 최종 주간 리포트 작성 (Agent G 활용)
    weekly_markdown = run_chief_strategist_agent(weekly_outline, rag_context)

    week_num = (today.day - 1) // 7 + 1
    safe_filename = f"{year_month}-W{week_num}_주간_경제_총결산.md"
    save_path = os.path.join(target_dir, safe_filename)
    
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(weekly_markdown)
        
    print(f"\n🎉 [완료] RAG 기반 주간 총결산 리포트 생성 완료: {save_path}")

if __name__ == "__main__":
    main()