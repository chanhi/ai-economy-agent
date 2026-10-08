import json

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