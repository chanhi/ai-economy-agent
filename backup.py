import urllib.parse
import requests
import trafilatura
import re
import os
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🔑 API 키 설정 (환경 변수에서 안전하게 가져오기)
# ==========================================
# os.getenv("변수명")을 사용하면 코드에 키를 노출하지 않고도 값을 가져올 수 있습니다.
NCP_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NCP_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 필수 키 누락 방지 로직 (옵션)
if not all([NCP_CLIENT_ID, NCP_CLIENT_SECRET, GEMINI_API_KEY]):
    raise ValueError("⚠️ .env 파일에 API 키가 누락되었습니다! 설정을 확인하세요.")

# ==========================================
# 1. 네이버 뉴스 수집 (데이터 파이프라인)
# ==========================================
def get_ncloud_api_news_with_text(keyword, max_articles=3):
    encoded_query = urllib.parse.quote(keyword)
    api_url = f"https://naverapihub.apigw.ntruss.com/search/v1/news?query={encoded_query}&display={max_articles}&sort=sim"
    
    api_headers = {
        "X-NCP-APIGW-API-KEY-ID": NCP_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NCP_CLIENT_SECRET
    }
    
    print(f"📡 NAVER API HUB에서 '{keyword}' 뉴스를 가져오는 중...")
    try:
        response = requests.get(api_url, headers=api_headers)
        response.raise_for_status()
        res_json = response.json()
    except Exception as e:
        print(f"❌ API 통신 에러: {e}")
        return []

    news_data = []
    items = res_json.get('items', [])
    
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    }

    for item in items:
        clean_title = re.sub(r'<.*?>', '', item['title']).replace('&quot;', '"').replace('&apos;', "'")
        original_link = item['originallink']
        
        print(f"🔄 '{clean_title}' 본문 추출 중...")
        try:
            article_response = requests.get(original_link, headers=req_headers, timeout=10)
            if article_response.status_code == 200:
                article_text = trafilatura.extract(article_response.text)
                if article_text:
                    news_data.append({
                        "title": clean_title,
                        "link": original_link,
                        "text": article_text
                    })
                    print("  ✅ 추출 성공!")
        except Exception as e:
            print(f"  ❌ 접속 에러: {e}")

    return news_data

# ==========================================
# 2. Gemini 요약 및 옵시디언 저장 (지능 파이프라인)
# ==========================================
def create_obsidian_note(news_data, target_keyword):
    if not news_data:
        print("⚠️ 수집된 뉴스가 없어 요약을 건너뜁니다.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # LLM에게 먹일 텍스트 조립
    context_text = ""
    for idx, article in enumerate(news_data, 1):
        context_text += f"[{idx}] 기사 제목: {article['title']}\n"
        context_text += f"원본 링크: {article['link']}\n"
        
        # 💡 핵심 수정: 기사 본문이 너무 길어 토큰 한도에 걸리지 않도록 앞부분 2000자만 자릅니다.
        truncated_text = article['text'][:2000]
        context_text += f"기사 본문: {truncated_text}\n\n"

    today_str = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
    너는 주식 투자를 막 시작한 초보자를 위한 '친절하고 똑똑한 경제 튜터'야.
    아래에 제공된 오늘({today_str})의 '{target_keyword}' 관련 경제 뉴스 본문들을 읽고, 
    사용자가 Obsidian(옵시디언) 앱에서 바로 읽고 보관하기 가장 완벽한 형태의 마크다운(Markdown) 문서로 정리해 줘.

    [작성 가이드 및 포맷]
    1. 문서 맨 위에는 옵시디언 프로퍼티(YAML frontmatter)를 작성해 줘. 
       - tags: [경제, {target_keyword}, 데일리요약]
       - date: {today_str}
    2. # 📰 오늘의 핵심 요약
       - 전체 기사의 핵심적인 시장 흐름을 3~5줄로 요약.
    3. # 📈 주요 이슈 분석
       - 투자 관점에서 알아야 할 중요 포인트 3가지를 글머리 기호(-)와 굵은 글씨(**)를 활용해 정리.
    4. # 📖 오늘의 경제 단어장
       - 본문에 등장한 어려운 경제/금융 용어(예: 랠리, 어닝 서프라이즈, 매파 등)를 3~5개 추출.
       - 단어는 옵시디언 백링크 형식인 `[[단어]]` 형태로 작성할 것.
       - 단어의 설명은 마크다운 인용구(`>`)를 사용하여 초보자도 이해할 수 있는 쉬운 비유를 들어 설명할 것.
    5. # 🔗 참고 기사
       - 제공된 원문 링크들을 리스트 형태로 보기 좋게 나열.

    [오늘의 뉴스 데이터]:
    {context_text}
    """

    print("🧠 Gemini가 뉴스를 분석하고 옵시디언 노트를 작성 중입니다...")
    
    response = client.models.generate_content(
        model='gemini-flash-latest', 
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3)
    )

    # 3. 로컬 마크다운 파일로 저장 (폴더 분리)
    output_dir = "obsidian_notes"
    os.makedirs(output_dir, exist_ok=True) # 폴더가 없으면 자동 생성
    
    filename = os.path.join(output_dir, f"{today_str}_{target_keyword}_경제요약.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(response.text)
        
    print(f"🎉 성공! 옵시디언 노트 생성 완료: {filename}")

# ==========================================
# 메인 실행부
# ==========================================
if __name__ == "__main__":
    keyword = "금리인하" # 원하는 주제로 변경 (예: 삼성전자, AI, 미국증시)
    
    # 1. 뉴스 데이터 수집
    articles = get_ncloud_api_news_with_text(keyword, max_articles=4)
    
    # 2. 요약 및 노트 생성
    create_obsidian_note(articles, keyword)