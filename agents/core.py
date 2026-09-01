import json
import time
from datetime import datetime
from google import genai
from google.genai import types
from google.genai.errors import APIError
from config import GEMINI_API_KEY

HEAVY_MODELS = [
    'gemini-flash-latest', 
    'models/gemini-3.6-flash',
    'models/gemini-3.5-flash',
    'models/gemini-2.5-flash'
]

LITE_MODELS = [
    'models/gemini-3.5-flash-lite', 
    'models/gemini-2.5-flash-lite', 
    'gemini-1.5-flash-8b'
]

def smart_gemini_call(prompt, config_params, model_tier="heavy", retries=2):
    client = genai.Client(api_key=GEMINI_API_KEY)
    target_models = LITE_MODELS if model_tier == "lite" else HEAVY_MODELS
    
    for model_name in target_models:
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_params)
                )
                return response.text
            except APIError as e:
                error_msg = str(e)
                if '429' in error_msg or '503' in error_msg or '500' in error_msg:
                    err_type = "429 한도 초과" if '429' in error_msg else "503 서버 과부하"
                    print(f"⚠️ [{err_type}] {model_name}({model_tier}) 상태 불안정. (시도 {attempt+1}/{retries})")
                    
                    if attempt < retries - 1:
                        wait_time = 65 if '429' in error_msg else 10
                        print(f"⏳ {wait_time}초 대기 후 재시도합니다...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"🔄 {model_name} 응답 실패. 다음 {model_tier} 모델로 전환합니다.")
                        break
                else:
                    print(f"❌ API 에러: {e}")
                    raise e
                    
    raise Exception(f"🚨 사용 가능한 모든 {model_tier} 모델의 한도가 초과되었거나 에러가 발생했습니다.")


def run_desk_agent(all_news, target_count=8):
    news_context = ""
    for news in all_news:
        news_context += f"[{news['id']}] {news['title']} | 요약: {news['description']}\n"

    prompt = f"""
    너는 글로벌 투자 은행의 수석 매크로 에디터다. 
    제공된 뉴스 목록을 광범위하게 분석하여:
    1. 오늘 시장을 관통하는 가장 핵심적인 키워드 1개
    2. 전체 거시 경제 흐름과 시장 관전 포인트(Market Overview) 2~3줄
    3. 주식/투자 시장에 가장 큰 파급력을 가질 핵심 기사 {target_count}개를 선별해라.

    [기사 선별 최우선 규칙 (우선순위)]
    1. 시장의 방향성을 결정짓는 '초대형 일정' (예: M7(엔비디아, 애플 등) 빅테크 실적 발표, FOMC, CPI 지표 발표)은 발견 즉시 반드시 포함할 것.
    2. 단순 하락/상승 팩트보다, 상승/하락의 '원인(기대감, 경계심 등)'을 다룬 시황 기사를 우대할 것.

    [뉴스 데이터]
    {news_context}
    
    응답형식(JSON):
    {{
        "today_keyword": "오늘의 핵심 키워드",
        "market_overview": "오늘 시장 흐름 종합 요약",
        "top_news": [
            {{"id": "기사ID", "reason": "선택 이유"}}
        ]
    }}
    """
    print(f"🧑‍💼 [Agent A: 데스크] Lite 모델로 {len(all_news)}개 뉴스 중 핵심 기사 {target_count}개 선별 중...")
    
    result_text = smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.2, "response_mime_type": "application/json"},
        model_tier="lite"
    )
    return json.loads(result_text)


def run_analyst_agent(article_info, recent_memory):
    full_text = article_info.get('full_text', '')

    prompt = f"""
    너는 월스트리트 경력 20년의 수석 거시경제/주식 애널리스트다. 
    기사 본문 전문을 정독하고 입체적인 분석 리포트를 작성하라. (영문 기사는 완벽한 한국어로 번역/의역할 것)

    [최근 시장 흐름 (기억)]
    {recent_memory}

    [기사 정보]
    제목: {article_info['title']}
    본문 전문:
    {full_text}
    
    [분석 지침]
    1. thinking_process: [최근 시장 흐름]과 비교하여 기존 추세 지속인지, 변곡점인지 추론해라.
    2. summary: [핵심 팩트] - [발생 배경/원인] - [시장 영향 및 수치 분석] - [향후 전망]으로 상세히 구성하라.
    3. affected_sectors: 호재/악재를 받는 구체적 섹터(테마)를 명시하라.

    응답형식(JSON):
    {{
        "id": "{article_info['id']}",
        "thinking_process": "...",
        "summary": [
            "📌 [핵심 팩트] ...",
            "🔍 [배경/원인] ...",
            "📊 [영향/수치] ...",
            "🎯 [향후 전망] ..."
        ],
        "affected_sectors": ["섹터명1", "섹터명2"],
        "terms": [{{"term": "용어", "explanation": "비유를 통한 쉬운 설명"}}]
    }}
    """
    print(f"🧑‍🏫 [Agent B] '{article_info['title'][:25]}...' 전문 딥다이브 분석 중...")
    
    result_text = smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.2, "response_mime_type": "application/json"},
        model_tier="heavy"
    )
    return json.loads(result_text)


def run_editor_agent(merged_data, agent_a_data, macro_indicators, feedback=""):
    dynamic_keyword = agent_a_data.get('today_keyword', '주요이슈')
    market_overview = agent_a_data.get('market_overview', '')

    report_context = ""
    for idx, item in enumerate(merged_data, 1):
        report_context += f"[{idx}] 기사 제목: {item['title']}\n"
        report_context += f"선정 이유: {item['reason']}\n"
        report_context += f"수혜/피해 섹터: {', '.join(item.get('affected_sectors', []))}\n"
        report_context += f"심층 분석 내용:\n" + "\n".join([f"  - {s}" for s in item.get('summary', [])]) + "\n"
        
        term_strings = []
        for t in item.get('terms', []):
            if isinstance(t, dict):
                term_strings.append(f"{t.get('term', '')}({t.get('explanation', '')})")
            elif isinstance(t, str):
                term_strings.append(t)
        report_context += f"용어 해설: {', '.join(term_strings)}\n"
        report_context += f"원문 링크: {item['link']}\n"
        report_context += "=" * 40 + "\n"

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    feedback_instruction = ""
    if feedback:
        feedback_instruction = f"\n🚨 [수석 검수자 지시사항]: 이전 작성본에 문제가 있습니다. 다음 피드백을 반드시 반영하여 전면 재작성하십시오 -> {feedback}\n"

    prompt = f"""
    너는 대형 투자은행의 수석 리서치 센터장이다.
    거시 지표와 {len(merged_data)}개 핵심 이슈의 심층 분석 데이터를 집대성하여, 완성도 높은 '일간 종합 경제 리포트'를 마크다운으로 작성하라.
    전문적이고 신뢰감 있는 문어체('합니다/입니다')를 사용하라.
    {feedback_instruction}

    [오늘의 거시 지표] {macro_indicators}
    [데스크 종합 시황] {market_overview}
    [심층 분석 데이터]
    {report_context}

    [마크다운 구조 지침 및 옵시디언 고도화]
    ---
    tags: [경제일간리포트, {dynamic_keyword}]
    date: {today_str}
    market_phase: (현재 시장 상황을 추론하여 Bull / Bear / Sideways 중 1개만 영문으로 작성)
    ---
    # 🏛️ Daily Macro Report: {dynamic_keyword}

    > **💡 Desk's Executive Summary:** {market_overview}

    ## 📊 글로벌 매크로 지표 브리핑
    - 수치 정리 및 코멘트

    ## 📑 심층 분석 리포트 (총 {len(merged_data)}선)
    (각 기사별 소제목(###), 선정 이유, 영향 섹터, 팩트/배경/전망)

    ## 📖 오늘의 금융/경제 단어장
    (용어 사전)

    ## 🔗 출처 및 참고 기사

    [💡 백링크(Backlink) 강제 규칙]
    - 본문에 등장하는 모든 '국가명', '기업명(엔비디아, 애플 등)', '거시 지표명(CPI, 금리, FOMC 등)', '주요 경제 용어'는 무조건 양옆에 대괄호를 두 번 씌워 옵시디언 백링크 양식 `[[단어]]` 로 작성하라.
    - 예시: "오늘 [[미국]] 증시는 [[엔비디아]]의 실적 발표와 [[연준]]의 [[금리]] 인하 기대감에..."
    """
    print("👨‍💼 [Agent C: 편집장] Lite 모델로 대형 일간 종합 리포트 조판 중...")
    
    return smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.3},
        model_tier="lite"
    )

# ==========================================
# 📊 8. 에이전트 H (포트폴리오 설계사)
# ==========================================
def run_portfolio_architect_agent(macro_report):
    prompt = f"""
    너는 글로벌 톱티어 자산운용사의 수석 포트폴리오 설계사(Portfolio Architect)다.
    아래 제공된 경제 리포트를 심층 분석하여, 다가오는 시장 환경에 대비하기 위한 '섹터별 포트폴리오 비중 조절 전략'을 수립하라.

    [분석 대상 리포트]
    {macro_report}

    [사전 정의된 평가 대상 섹터]
    1. 대형 기술주 (Big Tech)
    2. 반도체 및 AI (Semiconductors & AI)
    3. 헬스케어 (Healthcare)
    4. 금융 (Financials)
    5. 에너지 (Energy)
    6. 미국 장기 국채 (Long-term Treasuries)
    7. 현금성 자산 (Cash)

    [투자 성향별 전략 가이드]
    - 공격투자형 (Aggressive): 리스크를 감수하며 초과 수익을 추구하는 포지션
    - 안정투자형 (Conservative): 변동성을 방어하고 자본을 지키는 포지션

    위 섹터들에 대해 각각 '확대(Overweight)', '유지(Hold)', '축소(Underweight)' 의견을 제시하고 핵심 이유를 1줄로 간결하게 적어라.
    반드시 아래의 마크다운 표 형식만 출력하라. (다른 인사말이나 설명은 절대 생략할 것)

    ## 🧭 일간 포트폴리오 액션 플랜 (Action Plan)
    ### ⚔️ 공격투자형 (Aggressive)
    | 섹터 | 액션 | 핵심 근거 |
    | :--- | :---: | :--- |
    | 대형 기술주 | (확대/유지/축소) | (이유) |
    ... (7개 섹터 모두 작성) ...

    ### 🛡️ 안정투자형 (Conservative)
    | 섹터 | 액션 | 핵심 근거 |
    | :--- | :---: | :--- |
    ... (7개 섹터 모두 작성) ...
    """
    print("🧑‍💼 [Agent H: 설계사] Heavy 모델로 리포트 분석 및 투자 성향별 액션 플랜 수립 중...")
    
    # 전략 수립은 고도화된 추론이 필요하므로 Heavy 모델 배정
    return smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.2},
        model_tier="heavy"
    )


def run_reviewer_agent(markdown_report, macro_indicators):
    prompt = f"""
    너는 깐깐한 수석 검수자(Reviewer)다. 
    편집장이 방금 작성한 아래의 마크다운 리포트를 검사하라.
    
    [필수 검수 항목]
    1. 마크다운 맨 위에 YAML 프론트매터(tags, date)가 정확히 양식대로 포함되어 있는가?
    2. [오늘의 매크로 지표] '{macro_indicators}' 의 수치가 본문에 누락되거나 틀리게 적혀있지 않은가?
    3. 옵시디언 백링크 양식(`[[단어]]`)이 단어장에 잘 적용되었는가?

    [편집장이 작성한 리포트]
    {markdown_report}

    응답형식(JSON):
    {{
        "pass": true 또는 false,
        "feedback": "pass가 false일 경우, 편집장이 고쳐야 할 구체적인 지적 사항을 작성. true면 '완벽합니다' 작성."
    }}
    """
    print("🕵️‍♂️ [Agent D: 검수자] Lite 모델로 최종 리포트 품질 검수 중...")
    
    result_text = smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.1, "response_mime_type": "application/json"},
        model_tier="lite"
    )
    return json.loads(result_text)


def run_preprocessor_agent(article_info):
    full_text = article_info.get('full_text', '')
    
    prompt = f"""
    너는 투자 은행의 리서치 어시스턴트(Pre-processor)다.
    아래 수집된 기사 본문 원문에서 불필요한 광고, 언론사 정보, 관련 없는 텍스트(노이즈)를 완전히 제거하고, 
    오직 경제/주식 분석에 필요한 핵심 본문만 '완벽한 한국어'로 정리해서 반환하라.
    (원문이 영어라면 전문 번역/의역할 것. 요약하지 말고 본문의 디테일을 최대한 살릴 것.)

    [기사 원문]
    제목: {article_info['title']}
    본문: {full_text[:10000]} 

    응답형식: 어떠한 인사말이나 마크다운 없이, 정제된 한국어 본문 텍스트만 출력할 것.
    """
    print(f"🧹 [Agent E: 전처리] '{article_info['title'][:20]}...' 노이즈 제거 및 번역 중...")
    
    return smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.1},
        model_tier="lite"
    )


def run_memory_synthesizer_agent(raw_memory):
    if len(raw_memory) < 50:
        return raw_memory
        
    prompt = f"""
    너는 글로벌 거시경제 트렌드 분석가다.
    아래는 최근 며칠간 우리 시스템이 기록한 시장의 단편적인 기억(키워드와 시황)들이다.
    이 파편화된 정보들을 종합하여, "최근 시장을 지배하고 있는 거시경제 트렌드와 흐름의 변화"를 
    한 단락(3~4문장)의 완성된 맥락(Context)으로 합성하라.

    [과거 시장 기록]
    {raw_memory}

    응답형식: 어떠한 인사말 없이, 합성된 트렌드 분석 텍스트만 출력할 것.
    """
    print("🧠 [Agent F: 기억 합성] 파편화된 과거 기록을 거시적 트렌드로 엮어내는 중...")
    
    return smart_gemini_call(
        prompt=prompt, 
        config_params={"temperature": 0.2},
        model_tier="lite"
    )