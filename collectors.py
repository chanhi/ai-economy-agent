import re
import urllib.parse
import requests
import feedparser
from config import NCP_CLIENT_ID, NCP_CLIENT_SECRET
import trafilatura

def fetch_domestic_news(keyword, count=10):
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

def fetch_overseas_news(count=10):
    rss_url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
    news_list = []
    
    try:
        feed = feedparser.parse(rss_url)
        for idx, entry in enumerate(feed.entries[:count]):
            news_list.append({
                "id": f"US_{idx+1}",
                "source": "CNBC",
                "title": entry.title,
                "description": entry.summary if 'summary' in entry else "",
                "link": entry.link
            })
    except Exception as e:
        print(f"❌ CNBC 뉴스 수집 에러: {e}")
        
    return news_list

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