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
    - 월요일부터 금요일까지 시장의 분위기(투심, 기대감 등)가 어떤 이슈들로 인해 어떻게 변화해 왔는지 시간순/흐름순으로 입체적으로 분석. (단순 요약이 아닌 맥락의 연결)

    ## 📊 핵심 매크로 지표 리뷰
    - 이번 주에 발표된 주요 지표나 발언(환율, 금리, 인플레이션 등) 중 가장 파급력이 컸던 것들을 되짚어보고 그 의미를 해석.

    ## 🎯 수혜/피해 주요 섹터 결산
    - 이번 주 리포트들에 등장한 섹터들을 종합하여, 이번 주 가장 뜨거웠던 섹터와 타격을 입은 섹터를 정리.

    ## 🔮 다음 주 시장 관전 포인트 (Next Week Watchpoints)
    - 이번 주 흐름을 바탕으로, 다음 주 투자자들이 반드시 주의 깊게 지켜봐야 할 리스크나 기회 요인 2~3가지.
    """
    print("👑 [Agent G: 수석 전략가] Heavy 모델로 1주일 치 리포트 전문을 분석하여 주간 전략 수립 중...")
    
    return smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.3},
        model_tier="heavy"
    )

def main():
    print("📅 주간 경제 총결산 파이프라인을 시작합니다...")
    
    # 💡 config.py에 정의된 상수 사용
    if not os.path.exists(OBSIDIAN_OUTPUT_DIR):
        print("⚠️ 옵시디언 노트 폴더가 존재하지 않습니다.")
        return

    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    
    weekly_content = ""
    file_count = 0
    
    for filepath in glob.glob(os.path.join(OBSIDIAN_OUTPUT_DIR, "*.md")):
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

    year_month = today.strftime("%Y-%m")
    week_num = (today.day - 1) // 7 + 1
    
    safe_filename = f"{year_month}-W{week_num}_주간_경제_총결산.md"
    save_path = os.path.join(OBSIDIAN_OUTPUT_DIR, safe_filename)
    
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(weekly_markdown)
        
    print(f"\n🎉 [완료] 주간 총결산 리포트 생성 완료: {save_path}")

    # 💡 utils/notifier.py 모듈을 활용하여 디스코드 알림 전송 기능 활성화
    # send_discord_alert(
    #     keyword="주간 경제 총결산 (Weekly Macro Strategy)",
    #     overview="월~금요일까지의 거시 경제 흐름과 다음 주 관전 포인트가 정리되었습니다.",
    #     indicators="주간 리포트 본문 참조",
    #     filepath=save_path
    # )

if __name__ == "__main__":
    main()