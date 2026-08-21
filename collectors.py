import re
import urllib.parse
import requests
import feedparser
import trafilatura
import yfinance as yf
from config import NCP_CLIENT_ID, NCP_CLIENT_SECRET

# ==========================================
# 1. 국내 뉴스 수집 (네이버 API)
# ==========================================
def fetch_domestic_news(keyword, count=25):
    encoded_query = urllib.parse.quote(keyword)
    api_url = f"https://naverapihub.apigw.ntruss.com/search/v1/news?query={encoded_query}&display={count}&sort=sim"
    
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NCP_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NCP_CLIENT_SECRET
    }
    
    news_list = []
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        items = response.json().get('items', [])
        
        for idx, item in enumerate(items):
            title = re.sub(r'<.*?>', '', item['title']).replace('&quot;', '"').replace('&apos;', "'")
            desc = re.sub(r'<.*?>', '', item['description']).replace('&quot;', '"').replace('&apos;', "'")
            
            news_list.append({
                "id": f"KR_{idx+1}",
                "source": "Naver",
                "title": title,
                "description": desc,
                "link": item['originallink']
            })
    except Exception as e:
        print(f"❌ 네이버 뉴스 수집 에러: {e}")
        
    return news_list

# ==========================================
# 2. 해외 뉴스 수집 (CNBC, WSJ, Yahoo Finance)
# ==========================================
def fetch_overseas_news(count=30):
    # 💡 글로벌 핵심 경제 매체 3곳의 RSS 피드
    rss_urls = {
        "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "WSJ": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "YahooFinance": "https://finance.yahoo.com/news/rssindex"
    }
    
    news_list = []
    # 각 매체당 균등하게 뉴스를 배분하여 수집
    count_per_source = (count // len(rss_urls)) + 1
    
    try:
        for source_name, url in rss_urls.items():
            feed = feedparser.parse(url)
            for entry in feed.entries[:count_per_source]:
                # 일부 피드의 HTML 태그 찌꺼기를 정제합니다
                raw_desc = entry.get('summary', '')
                clean_desc = re.sub(r'<.*?>', '', raw_desc)
                
                news_list.append({
                    "id": f"US_{source_name}_{len(news_list)+1}",
                    "source": source_name,
                    "title": entry.title,
                    "description": clean_desc,
                    "link": entry.link
                })
    except Exception as e:
        print(f"❌ 해외 뉴스 수집 에러 ({source_name}): {e}")
        
    return news_list[:count] # 정확히 요청한 개수만큼만 잘라서 반환

# ==========================================
# 3. 뉴스 본문 추출 (Trafilatura)
# ==========================================
def fetch_article_text(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            text = trafilatura.extract(response.text)
            return text if text else ""
    except Exception as e:
        print(f"❌ 본문 추출 에러 ({url}): {e}")
    return ""

# ==========================================
# 📈 4. 실시간 거시 경제 지표 수집 (yfinance)
# ==========================================
def fetch_macro_indicators():
    indicators = {
        "S&P 500": "^GSPC",
        "원/달러 환율": "KRW=X",
        "미국 10년물 국채금리": "^TNX",
        "WTI 원유": "CL=F"
    }
    
    results = {}
    print("\n📈 실시간 거시 경제 지표를 수집 중입니다...")
    
    for name, ticker in indicators.items():
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="1d")
            
            if not hist.empty:
                latest_price = hist['Close'].iloc[-1]
                
                if name == "원/달러 환율":
                    results[name] = f"{latest_price:,.2f}원"
                elif "금리" in name:
                    results[name] = f"{latest_price:.3f}%"
                elif "원유" in name:
                    results[name] = f"${latest_price:.2f}"
                else:
                    results[name] = f"{latest_price:,.2f}"
            else:
                results[name] = "데이터 없음"
        except Exception as e:
            print(f"  ❌ {name} 지표 수집 에러: {e}")
            results[name] = "조회 실패"
            
    indicator_string = " | ".join([f"{k}: {v}" for k, v in results.items()])
    print(f"  ✅ 수집 완료: {indicator_string}")
    
    return indicator_string


# ==========================================
# 🧪 단위 테스트 (Unit Test) 실행 구역
# ==========================================
if __name__ == "__main__":
    print("=== 🇰🇷 1. 국내 뉴스 수집 테스트 ===")
    kr_test = fetch_domestic_news("경제 주식", count=3)
    for news in kr_test:
        print(f"[{news['source']}] {news['title']}")
        print(f"  🔗 {news['link']}\n")

    print("=== 🌎 2. 해외 뉴스 수집 테스트 ===")
    us_test = fetch_overseas_news(count=10)
    for news in us_test:
        print(f"[{news['source']}] {news['title']}")
        print(f"  🔗 {news['link']}\n")

    print("=== 📈 3. 거시 경제 지표 테스트 ===")
    indicators_test = fetch_macro_indicators()
    print(f"  👉 최종 텍스트: {indicators_test}\n")

    print("=== 🕸️ 4. 본문 추출(Trafilatura) 테스트 ===")
    if us_test:
        target_url = us_test[0]['link']
        print(f"타겟 URL: {target_url}")
        article_body = fetch_article_text(target_url)
        if article_body:
            print(f"✅ 성공! 추출된 본문 (앞 200자 미리보기):\n{article_body[:200]}...")
        else:
            print("❌ 본문 추출 실패 (보안이 강한 사이트이거나 연결 오류)")