import os
import re
from datetime import datetime
from config import OBSIDIAN_OUTPUT_DIR

def save_markdown_report(keyword, markdown_text):
    """최종 생성된 텍스트를 연월(YYYY-MM) 폴더에 분류하여 저장합니다."""
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    year_month = today.strftime("%Y-%m")
    
    # 💡 YYYY-MM 형태의 하위 폴더 경로 생성
    target_dir = os.path.join(OBSIDIAN_OUTPUT_DIR, year_month)
    os.makedirs(target_dir, exist_ok=True)
    
    safe_keyword = re.sub(r'[\\/*?:"<>|]', '_', keyword)
    filename = os.path.join(target_dir, f"{today_str}_{safe_keyword}_일간_종합_경제요약.md")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_text)
        
    print(f"\n🎉 [완료] 일간 종합 리포트 생성 완료: {filename}")
    return filename