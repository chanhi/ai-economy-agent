import os
import re
from datetime import datetime
from config import OBSIDIAN_OUTPUT_DIR

def save_markdown_report(keyword, markdown_text):
    """최종 생성된 텍스트를 Obsidian 마크다운 파일로 저장합니다."""
    os.makedirs(OBSIDIAN_OUTPUT_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 윈도우/리눅스 파일명 에러 방지를 위한 특수문자 제거
    safe_keyword = re.sub(r'[\\/*?:"<>|]', '_', keyword)
    filename = os.path.join(OBSIDIAN_OUTPUT_DIR, f"{today_str}_{safe_keyword}_일간_종합_경제요약.md")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_text)
        
    print(f"\n🎉 [완료] 일간 종합 리포트 생성 완료: {filename}")
    return filename