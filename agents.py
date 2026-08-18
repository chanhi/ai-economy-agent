import json
import time
from datetime import datetime
from google import genai
from google.genai import types
from google.genai.errors import APIError
from config import GEMINI_API_KEY

# 💡 가용한 모델 리스트를 우선순위대로 배치 (최신 -> 구형)
AVAILABLE_MODELS = [
    'gemini-flash-latest', 
    'models/gemini-3.6-flash',
    'models/gemini-2.5-flash'
]

# ==========================================
# 🛡️ 1. 스마트 LLM 호출기 (재시도 및 모델 스위칭 기능 내장)
# ==========================================
def smart_gemini_call(prompt, config_params, retries=2):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    for model_name in AVAILABLE_MODELS:
        for attempt in range(retries):
            try:
                # API 호출
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_params)
                )
                return response.text
                
            except APIError as e:
                error_msg = str(e)
                if '429' in error_msg:
                    print(f"⚠️ [429 에러] {model_name} RPM/RPD 초과. (시도 {attempt+1}/{retries})")
                    if attempt < retries - 1:
                        print("⏳ 1분(60초) 대기 후 재시도합니다...")
                        time.sleep(62) # 분당 제한(RPM) 해결을 위한 62초 대기
                        continue
                    else:
                        print(f"🔄 {model_name} 일일 한도 소진 의심. 다음 모델로 전환합니다.")
                        break # 현재 모델 포기, 다음 모델로 넘어감
                else:
                    print(f"❌ 알 수 없는 API 에러: {e}")
                    raise e
                    
    raise Exception("🚨 사용 가능한 모든 Gemini 모델의 한도가 초과되었거나 에러가 발생했습니다.")

# ==========================================
# 🕵️‍♂️ 2. 에이전트 A (데스크) - 키워드 도출 추가
# ==========================================
def run_desk_agent(all_news):
    news_context = ""
    for news in all_news:
        news_context += f"ID:{news['id']} | 출처:{news['source']} | 제목:{news['title']}\n요약:{news['description']}\n---\n"

    prompt = f"""
    너는 글로벌 투자 은행 수석 편집장이야. 아래 뉴스들을 분석하여 다음 두 가지를 수행해:
    1. 오늘 시장을 관통하는 가장 핵심적인 '오늘의 키워드' 1개를 선정해 (예: 엔캐리청산, 물가지수, AI거품론 등).
    2. 주식 시장에 가장 큰 영향을 미칠 핵심 뉴스 딱 3개만 선별해. 중복 기사는 하나만 선택해.
    
    [뉴스]
    {news_context}
    
    반드시 아래 JSON 형식으로만 응답해.
    {{
        "today_keyword": "선정된 1개의 키워드",
        "top_news": [
            {{"id": "기사ID", "reason": "선택이유 1줄"}}
        ]
    }}
    """
    print("🧑‍💼 [Agent A: 데스크] 오늘의 키워드 도출 및 기사 3개 선별 중...")
    
    result_text = smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.2, "response_mime_type": "application/json"}
    )
    return json.loads(result_text)

# ==========================================
# 🧑‍🏫 3. 에이전트 B (분석가)
# ==========================================
def run_analyst_agent(article_info):
    safe_text = article_info['full_text'][:2000] # TPM 방어 및 속도 향상을 위해 2000자로 타이트하게 조정

    prompt = f"""
    심층 경제 분석가로서 아래 기사를 완벽히 분석해 줘. 영어 기사는 한국어로 번역할 것.
    [기사] 제목: {article_info['title']} \n 본문: {safe_text}
    반드시 아래 JSON 형식으로 응답해.
    {{
        "id": "{article_info['id']}",
        "summary": ["핵심 1줄", "핵심 2줄", "핵심 3줄"],
        "terms": [{{"term": "어려운용어", "explanation": "초보자용 비유설명"}}]
    }}
    """
    print(f"🧑‍🏫 [Agent B] '{article_info['title']}' 분석 중...")
    
    result_text = smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.2, "response_mime_type": "application/json"}
    )
    return json.loads(result_text)

# ==========================================
# 👨‍💼 4. 에이전트 C (편집장) - 파일명/태그용 키워드 수신
# ==========================================
def run_editor_agent(merged_data, dynamic_keyword):
    report_context = ""
    for item in merged_data:
        report_context += f"기사 제목: {item['title']} (선정 이유: {item['reason']})\n"
        report_context += f"3줄 요약: {' / '.join(item['summary'])}\n"
        term_strings = [f"{t['term']}({t['explanation']})" for t in item.get('terms', [])]
        report_context += f"용어: {', '.join(term_strings)}\n원본 링크: {item['link']}\n---\n"

    today_str = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
    수석 경제 에디터로서 제공된 3개의 기사 데이터를 바탕으로 옵시디언 마크다운 리포트를 작성해.
    1. 문서 위 YAML 프로퍼티: 
       - tags: [경제뉴스, {dynamic_keyword}]
       - date: {today_str}
       - 오늘의키워드: {dynamic_keyword}
    2. # 📰 오늘의 주요 경제 뉴스: 각 기사별 제목(##), 선정이유, 핵심 3줄 요약
    3. # 📖 오늘의 경제 단어장: 용어들을 모아 백링크 `[[단어]]` 적용
    4. # 🔗 참고 자료: 기사 링크 나열
    [데이터]
    {report_context}
    """
    print("👨‍💼 [Agent C: 편집장] 최종 마크다운 리포트 종합 중...")
    
    return smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.3}
    )