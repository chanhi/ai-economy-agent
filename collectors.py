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
# 5. 주요 빅테크 실적 발표 캘린더 (Alpha Vantage)
# ==========================================
def fetch_major_earnings_schedule():
    import csv
    import requests
    from datetime import datetime, timedelta
    from config import ALPHA_VANTAGE_API_KEY
    
    # 💡 토큰 절약을 위해 시장 파급력이 거대한 '핵심 티커'만 필터링합니다. 
    # (필요시 TSMC, ASML 등 원하는 티커를 자유롭게 추가하세요)
    TARGET_SYMBOLS = {'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'INTC', 'NFLX'}
    
    # horizon=3month로 가져오면 향후 3개월치 일정이 CSV로 반환됩니다.
    url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey={ALPHA_VANTAGE_API_KEY}"
    
    upcoming_earnings = []
    
    try:
        with requests.Session() as s:
            download = s.get(url)
            download.raise_for_status()
            
            # API 결과가 CSV 형태이므로 디코딩하여 파싱합니다.
            decoded_content = download.content.decode('utf-8')
            csv_reader = csv.DictReader(decoded_content.splitlines(), delimiter=',')
            
            # 오늘부터 딱 일주일 치(7일) 일정만 필터링
            today = datetime.now().date()
            end_date = today + timedelta(days=7)
            
            for row in csv_reader:
                try:
                    report_date = datetime.strptime(row['reportDate'], '%Y-%m-%d').date()
                    symbol = row['symbol']
                    
                    # 기간 안에 있고, 타겟 티커 리스트에 포함된 경우만 추출
                    if today <= report_date <= end_date and symbol in TARGET_SYMBOLS:
                        upcoming_earnings.append(f"- {report_date} : {symbol} ({row['name']}) 실적 발표")
                except Exception:
                    continue # 날짜 형식이 안 맞거나 빈 값인 행은 무시
                    
    except Exception as e:
        print(f"❌ 실적 캘린더 수집 에러: {e}")
        return "실적 일정 데이터를 불러오지 못했습니다."
        
    if upcoming_earnings:
        return "\n".join(upcoming_earnings)
    else:
        return "이번 주 예정된 주요 빅테크(M7 등) 실적 발표 없음."

# ==========================================
# 6. 일일 미국 시장 주도주 수집 (Alpha Vantage)
# ==========================================
def fetch_top_movers():
    import requests
    from config import ALPHA_VANTAGE_API_KEY
    
    url = f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={ALPHA_VANTAGE_API_KEY}"
    
    try:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        
        # 💡 일일 호출 한도(25회) 초과 시 안내 메시지 처리
        if "Information" in data:
            print("⚠️ Alpha Vantage API 한도 초과입니다.")
            return "주도주 데이터 수집 불가 (API 한도 초과)"
            
        # 토큰 절약을 위해 상위 5개 종목의 티커와 등락률만 예쁘게 포매팅하는 내부 함수
        def format_stocks(stock_list, count=5):
            if not stock_list: 
                return "데이터 없음"
            
            result = []
            for stock in stock_list[:count]:
                ticker = stock.get('ticker', '')
                change_pct = stock.get('change_percentage', '')
                # 예: NVDA (+4.5%)
                result.append(f"{ticker} ({change_pct})")
            return ", ".join(result)
            
        top_gainers = format_stocks(data.get('top_gainers', []))
        top_losers = format_stocks(data.get('top_losers', []))
        most_active = format_stocks(data.get('most_actively_traded', []))
        
        summary = (
            f"- 🚀 급등주 (Top Gainers): {top_gainers}\n"
            f"- 📉 급락주 (Top Losers): {top_losers}\n"
            f"- 🔥 거래량 상위 (Most Active): {most_active}"
        )
        return summary
        
    except Exception as e:
        print(f"❌ 주도주 수집 에러: {e}")
        return "시장 주도주 데이터를 불러오지 못했습니다."