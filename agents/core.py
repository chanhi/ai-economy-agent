import re
import time
from datetime import datetime
from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from utils.parser import safe_json_loads, validate_daily_markdown
from agents.schemas import (
    HourlyFilterSchema,
    DeskSchema,
    AnalystSchema,
    EditorSynthesisSchema,
    ReviewerSchema,
    RagAnswerSchema,
)

HEAVY_MODELS = [
    "models/gemini-flash-latest",
    "models/gemini-3.8-flash",
    "models/gemini-3.7-flash",
    "models/gemini-3.6-flash",
    "models/gemini-3.5-flash",
]

LITE_MODELS = [
    "models/gemini-flash-lite-latest",
    "models/gemini-3.5-flash-lite",
    "models/gemini-3.1-flash-lite",
    "models/gemini-2.5-flash-lite",
]

# 파이프라인 실행 중 발생한 재시도/폴백 횟수 추적기 (관측성 메트릭용)
_FALLBACK_COUNT = 0


def reset_fallback_count():
    global _FALLBACK_COUNT
    _FALLBACK_COUNT = 0


def get_fallback_count() -> int:
    return _FALLBACK_COUNT


def smart_gemini_call(prompt, config_params, model_tier="heavy", retries=2, response_schema=None):
    global _FALLBACK_COUNT
    client = genai.Client(api_key=GEMINI_API_KEY)
    target_models = LITE_MODELS if model_tier == "lite" else HEAVY_MODELS

    merged_config = dict(config_params or {})
    if response_schema is not None:
        merged_config["response_mime_type"] = "application/json"
        merged_config["response_schema"] = response_schema

    for model_idx, model_name in enumerate(target_models):
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**merged_config),
                )
                return response.text

            except Exception as e:
                _FALLBACK_COUNT += 1
                error_msg = str(e)

                if "429" in error_msg or "503" in error_msg or "500" in error_msg:
                    err_type = "429 한도 초과" if "429" in error_msg else "50X 서버 과부하"
                    print(f"⚠️ [{err_type}] {model_name}({model_tier}) 상태 불안정. (시도 {attempt+1}/{retries})")

                    if attempt < retries - 1:
                        wait_time = 65 if "429" in error_msg else 10
                        print(f"⏳ {wait_time}초 대기 후 재시도합니다...")
                        time.sleep(wait_time)
                        continue
                    else:
                        if model_idx < len(target_models) - 1:
                            print(f"🔄 {model_name} 응답 실패. 다음 {model_tier} 모델로 전환합니다.")
                        break
                else:
                    print(f"⏩ [{model_name}] 에러 발생({error_msg[:60]}...). 즉시 다음 모델로 전환합니다.")
                    break

    print(f"🚨 [치명적 오류] 사용 가능한 모든 {model_tier} 모델이 응답하지 않습니다.")
    return "{}"


def run_desk_agent(all_news, target_count=13, macro_indicators=""):
    news_context = ""
    for news in all_news:
        news_context += f"ID:{news['id']} | 출처:{news.get('source', '')} | 제목:{news['title']} | 요약:{news['description'][:120]}\n"

    prompt = f"""
    너는 글로벌 투자 은행의 수석 매크로 에디터다.
    제공된 실시간 거시 지표와 뉴스 풀을 종합 분석하여 다음을 도출해라:
    1. today_keyword: 오늘 시장을 관통하는 핵심 키워드 1개 (파일명 안전을 위해 슬래시·물음표 제외)
    2. market_overview: 전체 거시 경제 흐름과 관전 포인트 2~3문장 ('합니다/입니다' 문어체, 국가·기업·지표·섹터명에 `[[단어]]` 백링크 필수 적용)
    3. sentiment_score & sentiment_label: 뉴스 톤앤매너와 VIX/금리/증시 등락을 반영한 오늘의 시장 심리 온도 (0=극단적 공포 ~ 50=중립 ~ 100=극단적 탐욕)
    4. selected_ids: 주식/투자 시장에 가장 파급력이 큰 핵심 기사 ID {target_count}개 선별

    [🚨 중복 제거 절대 규칙 - 매우 중요]
    - 선택한 {target_count}개의 기사는 모두 **서로 다른 주제/사건**이어야 한다.
    - '뉴욕증시 상승/하락 마감' 같은 일반 시황 종합 기사는 전체 중 **최대 1개만** 선택하라. 언론사만 다른 유사 기사를 중복 선택하면 절대 안 된다.
    - 반드시 아래 [뉴스 데이터]에 표시된 정확한 `ID:...` 문자열 그대로 반환하라.

    [실시간 거시 지표]
    {macro_indicators}

    [뉴스 데이터]
    {news_context}
    """
    print(f"🧑‍💼 [Agent A: 데스크] Lite 모델로 {len(all_news)}개 뉴스 중 중복 없는 핵심 기사 {target_count}개 및 투심 온도 산출 중...")

    result_text = smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.1},
        model_tier="lite",
        response_schema=DeskSchema,
    )
    return safe_json_loads(result_text, default_val={})


def run_analyst_agent(article_info, recent_memory, historical_precedents=""):
    full_text = article_info.get("full_text", "")
    precedent_block = (
        f"\n    [과거 유사 국면 선례 (Vector DB RAG)]\n    {historical_precedents}\n"
        if historical_precedents
        else ""
    )

    prompt = f"""
    너는 월스트리트 경력 20년의 수석 거시경제/주식 애널리스트다.
    기사 본문을 정독하고 입체적인 한국어 심층 분석 데이터를 작성하라.
    어조는 정중한 문어체('합니다/입니다')로 통일하고, 모든 국가명·기업명·거시지표·핵심용어·섹터명에는 반드시 옵시디언 백링크(`[[단어]]`)를 씌워라.

    [최근 5일 시장 흐름 (단기 기억)]
    {recent_memory}
    {precedent_block}
    [기사 정보]
    ID: {article_info['id']}
    제목: {article_info['title']}
    본문:
    {full_text}

    [분석 지침]
    1. selection_reason: 이 기사가 오늘 글로벌 거시경제 및 투자자에게 왜 중요한지 1문장으로 명확히 요약하라 (`[[백링크]]` 포함).
    2. thinking_process: [최근 5일 시장 흐름] 및 [과거 유사 국면 선례]와 대조하여 기존 추세 지속인지 변곡점인지 추론하라.
    3. summary: 정확히 아래 4개 접두어로 시작하는 상세 문장 4개로 구성하라 (`[[백링크]]` 적극 활용):
       - "📌 **[핵심 팩트]**: ..."
       - "🔍 **[배경/원인]**: ..."
       - "📊 **[영향/수치]**: ..."
       - "🎯 **[향후 전망]**: ..."
    4. affected_sectors: 호재/악재를 받는 구체적 섹터를 `[[섹터명]](호재)` 또는 `[[섹터명]](악재)` 형태로 명시하라.
    5. terms: 초보자도 이해할 수 있도록 비유를 곁들인 핵심 금융/경제 용어 1~2개를 추출하라.
    """
    print(f"🧑‍🏫 [Agent B] '{article_info['title'][:28]}...' 전문 딥다이브 분석 중...")

    result_text = smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.2},
        model_tier="heavy",
        response_schema=AnalystSchema,
    )
    return safe_json_loads(result_text, default_val=None)


def _format_backlink_sector(sector_str: str) -> str:
    s = sector_str.strip()
    if "[[" in s:
        return s
    # 예: "반도체(호재)" -> "[[반도체]](호재)"
    m = re.match(r"^([^\(\)]+)(\(.+\))$", s)
    if m:
        return f"[[{m.group(1).strip()}]]{m.group(2)}"
    return f"[[{s}]]" if s else s


def render_daily_markdown(
    merged_data: list[dict],
    agent_a_data: dict,
    editor_synthesis: dict,
    macro_indicators: str,
    market_extras: str = "",
) -> str:
    """
    [하이브리드 결정론적 조판기]
    LLM이 생성한 고부가가치 통찰(editor_summary, macro_commentary)과 개별 기사 분석 JSON을
    코드 레벨에서 오차 없이 결합하여 프론트매터·지표·링크 누락 확률을 0%로 만듭니다.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    dynamic_keyword = agent_a_data.get("today_keyword", "주요이슈").strip()
    safe_tag_keyword = re.sub(r"[\[\],]", " ", dynamic_keyword).strip()
    market_overview = agent_a_data.get("market_overview", "").strip()
    sentiment_score = agent_a_data.get("sentiment_score", 50)
    sentiment_label = agent_a_data.get("sentiment_label", "중립")

    market_phase = editor_synthesis.get("market_phase", "Sideways")
    if market_phase not in ("Bull", "Bear", "Sideways"):
        market_phase = "Sideways"
    editor_summary = editor_synthesis.get("editor_summary", market_overview).strip()
    macro_commentary = editor_synthesis.get("macro_commentary", [])

    lines = [
        "---",
        f"tags: [경제일간리포트, {safe_tag_keyword}]",
        f"date: {today_str}",
        f"market_phase: {market_phase}",
        f"sentiment_score: {sentiment_score}",
        f"sentiment_label: {sentiment_label}",
        "---",
        "",
        f"# 🏛️ Daily Macro Report: {dynamic_keyword}",
        "",
        f"> **💡 Desk's Executive Summary:** {market_overview}",
        "",
        f"> **💡 Editor's Deep Dive Summary:** {editor_summary}",
        "",
        f"> **🌡️ 시장 심리 온도:** {sentiment_score}점 ({sentiment_label}) | **📊 오늘의 매크로 지표:** {macro_indicators}",
        "",
        "## 📊 글로벌 매크로 지표 브리핑",
    ]

    if macro_commentary:
        for item in macro_commentary:
            clean_item = re.sub(r"^(?:[-•]\s*|\*\s+)", "", str(item).strip())
            if clean_item:
                lines.append(f"- {clean_item}")
    else:
        for seg in macro_indicators.split("|"):
            if seg.strip():
                lines.append(f"- {seg.strip()}")

    if market_extras and market_extras.strip():
        lines.append("")
        lines.append(market_extras.strip())

    lines.append("")
    lines.append(f"## 📑 심층 분석 리포트 (총 {len(merged_data)}선)")

    seen_terms = set()
    glossary_lines = []
    source_lines = []

    for idx, item in enumerate(merged_data, 1):
        title = item.get("title", f"핵심 이슈 {idx}").strip()
        reason = item.get("reason") or item.get("selection_reason") or ""
        sectors = [_format_backlink_sector(s) for s in item.get("affected_sectors", []) if s]
        sector_str = ", ".join(sectors) if sectors else "[[글로벌 증시 전반]]"

        lines.append("")
        lines.append(f"### {idx}. {title}")
        lines.append(f"- **선정 이유**: {reason}")
        lines.append(f"- **수혜/피해 섹터**: {sector_str}")
        lines.append("- **심층 분석 내용**:")

        for bullet in item.get("summary", []):
            clean_bullet = re.sub(r"^(?:[-•]\s*|\*\s+)", "", str(bullet).strip())
            if clean_bullet:
                lines.append(f"  - {clean_bullet}")

        for t in item.get("terms", []):
            if isinstance(t, dict):
                t_name = str(t.get("term", "")).strip()
                t_exp = str(t.get("explanation", "")).strip()
                norm_key = re.sub(r"[\[\]\s]", "", t_name).lower()
                if t_name and t_exp and norm_key not in seen_terms:
                    seen_terms.add(norm_key)
                    linked_term = t_name if "[[" in t_name else f"[[{t_name}]]"
                    glossary_lines.append(f"- **{linked_term}**: {t_exp}")

        link = item.get("link", "").strip()
        if link:
            safe_link_title = title.replace("[", "(").replace("]", ")")
            source_lines.append(f"- [{safe_link_title}]({link})")

    lines.append("")
    lines.append("## 📖 오늘의 금융/경제 단어장")
    if glossary_lines:
        lines.extend(glossary_lines)
    else:
        lines.append("- **[[거시경제(Macro)]]**: 금리, 환율, 물가 등 개별 기업을 넘어 경제 전체의 큰 흐름을 결정짓는 환경입니다.")

    lines.append("")
    lines.append("## 🔗 출처 및 참고 기사")
    if source_lines:
        lines.extend(source_lines)
    else:
        lines.append("- 출처 링크 없음")

    return "\n".join(lines)


def run_editor_agent(
    merged_data,
    agent_a_data,
    macro_indicators,
    feedback="",
    historical_precedents="",
    market_extras="",
):
    """
    Agent C (편집장):
    수석 센터장 종합 인사이트(editor_summary)와 거시 지표 브리핑(macro_commentary)만 구조화 JSON으로 생성한 뒤,
    render_daily_markdown()을 통해 무결점 마크다운으로 조립합니다.
    """
    market_overview = agent_a_data.get("market_overview", "")
    digest_lines = []
    for idx, item in enumerate(merged_data, 1):
        first_fact = item.get("summary", [""])[0] if item.get("summary") else ""
        digest_lines.append(
            f"[{idx}] {item.get('title', '')} | 선정이유: {item.get('reason', '')} | 요약: {first_fact[:180]}"
        )
    digest_context = "\n".join(digest_lines)

    feedback_instruction = f"\n🚨 [검수 피드백 반영 필수]: {feedback}\n" if feedback else ""
    precedent_block = f"\n[과거 유사 국면 선례]\n{historical_precedents}\n" if historical_precedents else ""

    prompt = f"""
    너는 대형 투자은행의 수석 리서치 센터장이다.
    오늘의 거시 지표와 {len(merged_data)}개 핵심 이슈 요약을 종합하여 다음 3가지 항목을 JSON으로 작성하라.
    어조는 전문적인 문어체('합니다/입니다')를 사용하고, 모든 국가명·기업명·거시지표·핵심용어·섹터명에는 반드시 `[[단어]]` 형태의 옵시디언 백링크를 적용하라.
    {feedback_instruction}

    [오늘의 거시 지표]
    {macro_indicators}

    [데스크 종합 시황]
    {market_overview}
    {precedent_block}
    [핵심 분석 기사 요약 ({len(merged_data)}선)]
    {digest_context}

    [작성 지침]
    1. market_phase: 오늘 시장 국면을 Bull, Bear, Sideways 중 하나로 판정하라.
    2. editor_summary: 데스크 시황과 핵심 기사들(필요 시 과거 선례 포함)의 인과관계를 꿰뚫는 3~4문장의 Deep Dive 종합 통찰을 작성하라 (`[[백링크]]` 필수).
    3. macro_commentary: [오늘의 거시 지표]에 포함된 각 지표의 정확한 수치와 등락률을 명시하고, 오늘 시장에서의 의미를 1문장씩 해설하라 (`[[백링크]]` 필수, 지표 누락 금지).
    """
    print("👨‍💼 [Agent C: 편집장] Lite 모델로 종합 인사이트 합성 및 하이브리드 조판 수행 중...")

    result_text = smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.25},
        model_tier="lite",
        response_schema=EditorSynthesisSchema,
    )
    synthesis = safe_json_loads(
        result_text,
        default_val={
            "market_phase": "Sideways",
            "editor_summary": market_overview,
            "macro_commentary": [],
        },
    )
    return render_daily_markdown(
        merged_data=merged_data,
        agent_a_data=agent_a_data,
        editor_synthesis=synthesis,
        macro_indicators=macro_indicators,
        market_extras=market_extras,
    )


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

    위 섹터들에 대해 각각 '확대', '유지', '축소' 중 하나만 액션 열에 적고 핵심 이유를 1줄로 간결하게 적어라.
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

    return smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.2},
        model_tier="heavy",
    )


def run_reviewer_agent(markdown_report, macro_indicators):
    """
    1단계: 파이썬 규칙 기반 결정론적 검수 (0.01초 소요, 토큰 0 소모)
    2단계: 규칙 검수 실패 시에만 구체적 오류 사유를 즉시 반환하여 재조판 유도
    """
    print("🕵️‍♂️ [Agent D: 검수자] 결정론적 양식·지표·백링크 무결성 검수 중...")
    is_valid, reason = validate_daily_markdown(markdown_report, macro_indicators)
    if not is_valid:
        return {"pass": False, "feedback": reason}

    # 주요 지표 키워드가 브리핑 섹션에 포함되었는지 추가 확인
    if "S&P 500" in macro_indicators and "S&P 500" not in markdown_report:
        return {"pass": False, "feedback": "매크로 지표 브리핑에 S&P 500 수치가 누락되었습니다."}

    return {"pass": True, "feedback": "완벽합니다."}


def run_preprocessor_agent(article_info):
    full_text = (article_info.get("full_text") or "").strip()
    title = article_info.get("title", "")

    # 💡 최적화: 본문 크롤링이 스킵되어 이미 짧은 한국어 요약문(<350자, 한글 포함)만 있는 경우 LLM 호출 없이 즉시 반환
    korean_chars = len(re.findall(r"[가-힣]", full_text))
    if len(full_text) < 350 and korean_chars > 30:
        print(f"⚡ [Agent E: 전처리 스킵] '{title[:20]}...' (단문 한국어 요약 직접 사용)")
        return full_text

    prompt = f"""
    너는 투자 은행의 리서치 어시스턴트(Pre-processor)다.
    아래 수집된 기사 본문 원문에서 불필요한 광고, 언론사 정보, 관련 없는 텍스트(노이즈)를 완전히 제거하고,
    오직 경제/주식 분석에 필요한 핵심 본문만 '완벽한 한국어'로 정리해서 반환하라.
    (원문이 영어라면 전문 번역/의역할 것. 요약하지 말고 본문의 수치와 디테일을 최대한 살릴 것.)

    [기사 원문]
    제목: {title}
    본문: {full_text[:8000]}

    응답형식: 어떠한 인사말이나 마크다운 헤더 없이, 정제된 한국어 본문 텍스트만 출력할 것.
    """
    print(f"🧹 [Agent E: 전처리] '{title[:22]}...' 노이즈 제거 및 한국어 정제 중...")

    return smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.1},
        model_tier="lite",
    )


def run_memory_synthesizer_agent(raw_memory):
    if len(raw_memory) < 50:
        return raw_memory

    prompt = f"""
    너는 글로벌 거시경제 트렌드 분석가다.
    아래는 최근 며칠간 우리 시스템이 기록한 시장의 단편적인 기억(키워드, 투심, 시황)들이다.
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
        model_tier="lite",
    )


def run_hourly_filter_agent(all_news, target_count=15):
    news_context = ""
    for idx, news in enumerate(all_news):
        news_context += f"[{idx}] ({news.get('source', '')}) {news['title']} | 요약: {news['description'][:150]}\n"

    prompt = f"""
    너는 투자 은행의 뉴스 큐레이터(1차 검문소)다.
    방금 수집된 {len(all_news)}개의 최신 뉴스 중에서 스팸, 단순 시황 중계(단순 숫자 나열), 광고성 기사, 중복 속보를 걸러내라.
    글로벌 거시경제와 주식 시장에 의미 있는 영향을 미칠 '진짜 뉴스' 최대 {target_count}개의 인덱스 번호만 선별하라.

    [뉴스 데이터]
    {news_context}
    """
    print(f"⏳ [Agent: 1차 큐레이터] Lite 모델(Structured Schema)로 {len(all_news)}개 중 유의미한 기사 선별 중...")

    result_text = smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.1},
        model_tier="lite",
        response_schema=HourlyFilterSchema,
    )
    return safe_json_loads(result_text, default_val={"selected_indices": []})


def run_theme_extractor_agent(weekly_outline):
    prompt = f"""
    아래는 이번 주 일간 경제 리포트들의 핵심 요약본이다.
    이를 바탕으로 이번 주 시장을 지배한 가장 중요한 거시경제 테마 3~4가지를 도출하라.
    설명 없이 반드시 쉼표(,)로만 구분된 짧은 키워드 형태로 출력하라.
    예시: 미국 국채금리 급등, AI 반도체 실적 충격, 고용 지표 둔화

    [주간 요약본]
    {weekly_outline}
    """
    print("🔍 [Agent I: 테마 추출기] Lite 모델로 이번 주 핵심 테마 키워드 도출 중...")
    result_text = smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.1},
        model_tier="lite",
    )
    return [theme.strip() for theme in result_text.split(",") if theme.strip()]


def run_chief_strategist_agent(weekly_outline, rag_context):
    prompt = f"""
    너는 월스트리트 최고 등급의 수석 매크로 전략가(Chief Strategist)다.
    아래 제공된 [이번 주 전체 흐름 요약]과 [RAG 테마별 심층 분석 데이터]를 바탕으로,
    파편화된 사건들을 연결하여 거대한 서사(Narrative)를 가진 '주간 경제 총결산' 리포트를 작성하라.
    어조는 '합니다/입니다'의 정중하고 전문적인 문어체를 사용해라.

    [이번 주 전체 흐름 요약 (Outline)]
    {weekly_outline}

    [RAG 테마별 심층 분석 데이터 (Deep Dives)]
    {rag_context}

    [마크다운 작성 포맷]
    ---
    tags: [주간경제결산, WeeklyStrategy]
    date: {datetime.now().strftime("%Y-%m-%d")}
    ---
    # 👑 Weekly Macro Strategy: 이번 주 시장을 지배한 거대한 흐름

    > **💡 Chief's Insight:** (이번 주 시장 전체를 관통하는 핵심 요약 2~3줄)

    ## 🌊 주간 핵심 테마 내러티브 (Core Themes)
    (각 테마는 반드시 `### 1. 테마 제목` 형태의 하위 헤더로 구분하여 시간순이 아닌 테마별 맥락과 인과관계로 입체 분석할 것)

    ## 📊 주요 매크로 지표 및 이벤트 리뷰
    - 파급력이 컸던 지표를 되짚어보고 의미를 해석.

    ## 🎯 수혜/피해 주요 섹터 결산
    - 마크다운 표(`| 구분 | 섹터 | 핵심 동인 및 주간 흐름 분석 |`) 형태로 정리.

    ## 🔮 다음 주 시장 관전 포인트 (Next Week Watchpoints)
    - 다음 주 주의 깊게 지켜봐야 할 리스크나 기회 요인 2~3가지.

    [💡 옵시디언 백링크(Backlink) 강제 규칙 - 매우 중요]
    - 본문에 등장하는 모든 '국가명', '기업명', '거시 지표명(CPI, 금리, 환율 등)', '주요 경제 용어', '섹터명'은 무조건 양옆에 대괄호를 씌워 `[[단어]]` 양식으로 작성하라.
    """
    print("👑 [Agent G: 수석 전략가] Heavy 모델로 테마 중심의 주간 전략 수립 중...")

    return smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.3},
        model_tier="heavy",
    )


def run_rag_qa_agent(question: str, retrieved_chunks: list[dict]) -> dict:
    """모바일 앱 `/api/ask` 전용: Vector DB 검색 결과를 바탕으로 근거 기반 Q&A 답변을 합성합니다."""
    if not retrieved_chunks:
        return {
            "answer": "질문과 관련된 과거 거시경제 리포트 데이터를 찾지 못했습니다. 다른 키워드로 질문해 보세요.",
            "key_points": [],
        }

    context_blocks = []
    for idx, c in enumerate(retrieved_chunks, 1):
        context_blocks.append(
            f"[근거 {idx} | 날짜: {c.get('date')} | 국면: {c.get('market_phase')} | 제목: {c.get('title')}]\n{c.get('content', '')[:800]}"
        )
    joined_context = "\n\n".join(context_blocks)

    prompt = f"""
    너는 'Economy Agent' 모바일 앱의 수석 거시경제 AI 어드바이저다.
    반드시 아래 제공된 [과거 리포트 검색 근거]에 기반하여 사용자의 질문에 명확하고 논리적인 한국어('합니다/입니다'체)로 답변하라.
    근거에 없는 수치를 지어내지 말고, 관련된 날짜나 시장 흐름을 자연스럽게 인용하라.

    [사용자 질문]
    {question}

    [과거 리포트 검색 근거]
    {joined_context}
    """
    result_text = smart_gemini_call(
        prompt=prompt,
        config_params={"temperature": 0.2},
        model_tier="lite",
        response_schema=RagAnswerSchema,
    )
    return safe_json_loads(
        result_text,
        default_val={
            "answer": "답변 생성 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "key_points": [],
        },
    )
