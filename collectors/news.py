import re
import urllib.parse
import requests
import feedparser
import trafilatura
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from config import NCP_CLIENT_ID, NCP_CLIENT_SECRET

def fetch_domestic_news(keyword, count=10):
    encoded_query = urllib.parse.quote(keyword)
    # 💡 1차: 관련도순(sim)으로 50개를 먼저 넉넉히 가져옵니다. (원본 NCP API 유지)
    api_url = f"https://naverapihub.apigw.ntruss.com/search/v1/news?query={encoded_query}&display=50&sort=sim"
    
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NCP_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NCP_CLIENT_SECRET
    }
    
    news_list = []
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        items = response.json().get('items', [])
        
        now = datetime.now(timezone.utc)
        
        for item in items:
            # 💡 2차: 발행일을 확인하여 24시간 이내의 최신 기사만 통과시킵니다.
            pub_date = parsedate_to_datetime(item['pubDate'])
            if now - pub_date > timedelta(hours=24):
                continue
                
            title = re.sub(r'<.*?>', '', item['title']).replace('&quot;', '"').replace('&apos;', "'")
            desc = re.sub(r'<.*?>', '', item['description']).replace('&quot;', '"').replace('&apos;', "'")
            
            news_list.append({
                "id": f"KR_{len(news_list)+1}",
                "source": "Naver",
                "title": title,
                "description": desc,
                "link": item['originallink']
            })
            
            # 지정한 개수(count)를 채우면 루프를 종료합니다.
            if len(news_list) >= count:
                break
                
    except Exception as e:
        print(f"❌ 네이버 뉴스 수집 에러: {e}")
        
    return news_list

def fetch_overseas_news(count=30):
    rss_urls = {
        "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "WSJ": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "YahooFinance": "https://finance.yahoo.com/news/rssindex"
    }
    
    news_list = []
    count_per_source = (count // len(rss_urls)) + 1
    
    try:
        for source_name, url in rss_urls.items():
            feed = feedparser.parse(url)
            for entry in feed.entries[:count_per_source]:
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
        
    return news_list[:count]

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