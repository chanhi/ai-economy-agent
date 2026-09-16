import os
import glob
from datetime import datetime, timedelta
from config import OBSIDIAN_OUTPUT_DIR
from agents.core import smart_gemini_call
# from notifier import send_discord_alert

# ==========================================
# 👑 에이전트 G (수석 전략가) - HEAVY 모델
# ==========================================
def run_chief_strategist_agent(weekly_reports_text):
    prompt = f"""
    너는 월스트리트 최고 등급의 수석 매크로 전략가(Chief Strategist)다.
    아래는 이번 주 월요일부터 금요일까지 우리 리서치 팀이 작성한 '일간 종합 경제 리포트' 전문이다.
    
    이 방대한 데이터를 모두 읽고, 파편화된 매일의 사건들을 연결하여 하나의 거대한 서사(Narrative)를 가진 '주간 경제 총결산(Weekly Macro Strategy)' 리포트를 작성하라.
    어조는 '합니다/입니다'의 정중하고 전문적인 문어체를 사용해라.

    [지난 5일간의 일간 리포트 전문]
    {weekly_reports_text}

    [마크다운 작성 포맷]
    ---
    tags: [주간경제결산, WeeklyStrategy]
    date: {datetime.now().strftime("%Y-%m-%d")}
    ---
    # 👑 Weekly Macro Strategy: 이번 주 시장을 지배한 거대한 흐름

    > **💡 Chief's Insight:** (이번 주 시장 전체를 관통하는 핵심 요약 2~3줄)

    ## 🌊 주간 시장 내러티브 (Narrative)
    - 시간순/흐름순으로 입체적으로 분석. (단순 요약이 아닌 맥락의 연결)

    ## 📊 핵심 매크로 지표 리뷰
    - 파급력이 컸던 지표를 되짚어보고 의미를 해석.

    ## 🎯 수혜/피해 주요 섹터 결산
    - 이번 주 가장 뜨거웠던 섹터와 타격을 입은 섹터 정리.

    ## 🔮 다음 주 시장 관전 포인트 (Next Week Watchpoints)
    - 다음 주 주의 깊게 지켜봐야 할 리스크나 기회 요인 2~3가지.

    [💡 옵시디언 백링크(Backlink) 강제 규칙 - 매우 중요]
    - 본문에 등장하는 모든 '국가명', '기업명', '거시 지표명(CPI, 금리, 환율 등)', '주요 경제 용어', '섹터명(반도체, 에너지 등)'은 무조건 양옆에 대괄호를 씌워 `[[단어]]` 양식으로 작성하라.
    - 자산 간의 **상관관계나 인과관계**를 설명할 때 백링크를 적극 활용하여, 일간 리포트들과 옵시디언 그래프 뷰에서 유기적으로 연결되도록 하라.
    - 예시: "이번 주 [[미국 국채금리]]의 급등은 [[빅테크]] 섹터의 밸류에이션 부담으로 이어지며 [[나스닥]] 하락을 견인했습니다."
    """
    print("👑 [Agent G: 수석 전략가] Heavy 모델로 1주일 치 리포트 전문을 분석하여 주간 전략 수립 중...")
    
    return smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.3},
        model_tier="heavy"
    )

def main():
    print("📅 주간 경제 총결산 파이프라인을 시작합니다...")
    
    if not os.path.exists(OBSIDIAN_OUTPUT_DIR):
        print("⚠️ 옵시디언 노트 폴더가 존재하지 않습니다.")
        return

    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    
    # 💡 주간 결산 파일도 현재 연월 폴더에 저장하기 위한 경로 준비
    year_month = today.strftime("%Y-%m")
    target_dir = os.path.join(OBSIDIAN_OUTPUT_DIR, year_month)
    os.makedirs(target_dir, exist_ok=True)
    
    weekly_content = ""
    file_count = 0
    
    # 💡 `**/*.md`와 `recursive=True`를 사용해 모든 연월 하위 폴더를 샅샅이 뒤집니다.
    search_pattern = os.path.join(OBSIDIAN_OUTPUT_DIR, "**", "*.md")
    for filepath in glob.glob(search_pattern, recursive=True):
        filename = os.path.basename(filepath)
        
        if "일간_종합_경제요약" in filename:
            try:
                date_str = filename[:10] 
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                if seven_days_ago <= file_date <= today:
                    with open(filepath, "r", encoding="utf-8") as f:
                        weekly_content += f"\n\n========================================\n"
                        weekly_content += f"📄 [리포트 날짜: {date_str}]\n"
                        weekly_content += f"========================================\n"
                        weekly_content += f.read()
                    file_count += 1
            except Exception as e:
                print(f"⚠️ 파일 날짜 파싱 오류 ({filename}): {e}")

    if file_count == 0:
        print("⚠️ 지난 1주일간 작성된 일간 리포트가 없어 주간 결산을 생략합니다.")
        return

    print(f"📚 최근 {file_count}개의 일간 리포트 텍스트를 성공적으로 병합했습니다.")

    weekly_markdown = run_chief_strategist_agent(weekly_content)

    week_num = (today.day - 1) // 7 + 1
    safe_filename = f"{year_month}-W{week_num}_주간_경제_총결산.md"
    save_path = os.path.join(target_dir, safe_filename)
    
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(weekly_markdown)
        
    print(f"\n🎉 [완료] 주간 총결산 리포트 생성 완료: {save_path}")

    # send_discord_alert(
    #     keyword="주간 경제 총결산 (Weekly Macro Strategy)",
    #     overview="월~금요일까지의 거시 경제 흐름과 다음 주 관전 포인트가 정리되었습니다.",
    #     indicators="주간 리포트 본문 참조",
    #     filepath=save_path
    # )

if __name__ == "__main__":
    main()