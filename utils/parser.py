import json
import re

def safe_json_loads(result_text: str, default_val=None):
    """LLM 응답 텍스트에서 마크다운 코드블록을 제거하고 안전하게 JSON으로 파싱합니다."""
    if default_val is None:
        default_val = {}

    if not result_text:
        return default_val

    try:
        clean_text = result_text.strip()
        if clean_text.startswith("```"):
            clean_text = clean_text.split("\n", 1)[-1]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

        return json.loads(clean_text)
    except Exception as e:
        print(f"⚠️ [JSON 파싱 에러] 기본값을 반환합니다: {e}")
        return default_val


def validate_daily_markdown(markdown_text: str, macro_indicators: str = "") -> tuple[bool, str]:
    """
    일간 마크다운 리포트가 파서 계약(server.py, vector_db.py, weekly_summary.py)을 100% 만족하는지
    LLM 호출 없이 결정론적 규칙으로 즉시 검증합니다.
    """
    if not markdown_text or len(markdown_text.strip()) < 300:
        return False, "리포트 본문 길이가 비정상적으로 짧습니다."

    required_patterns = [
        (r"^---\s*\n.*?date:\s*\d{4}-\d{2}-\d{2}.*?market_phase:\s*(Bull|Bear|Sideways).*?\n---", "YAML 프론트매터(date, market_phase) 누락 또는 형식 오류"),
        (r"# 🏛️ Daily Macro Report:\s*.+", "메인 타이틀('# 🏛️ Daily Macro Report:') 누락"),
        (r">\s*\*\*💡 Desk's Executive Summary:\*\*\s*.+", "Desk's Executive Summary 콜아웃 누락"),
        (r">\s*\*\*💡 Editor's Deep Dive Summary:\*\*\s*.+", "Editor's Deep Dive Summary 콜아웃 누락"),
        (r"## 📊 글로벌 매크로 지표 브리핑", "'## 📊 글로벌 매크로 지표 브리핑' 헤더 누락"),
        (r"## 📑 심층 분석 리포트", "'## 📑 심층 분석 리포트' 헤더 누락"),
        (r"###\s+1\.", "개별 기사 하위 섹션('### 1. ...') 누락"),
        (r"## 📖 오늘의 금융/경제 단어장", "'## 📖 오늘의 금융/경제 단어장' 헤더 누락"),
        (r"## 🔗 출처 및 참고 기사", "'## 🔗 출처 및 참고 기사' 헤더 누락"),
    ]

    for pattern, err_msg in required_patterns:
        if not re.search(pattern, markdown_text, re.DOTALL):
            return False, err_msg

    backlinks = re.findall(r"\[\[([^\[\]]+)\]\]", markdown_text)
    if len(backlinks) < 5:
        return False, f"옵시디언 백링크([[단어]]) 적용 개수가 부족합니다 (현재 {len(backlinks)}개)."

    return True, "완벽합니다."
