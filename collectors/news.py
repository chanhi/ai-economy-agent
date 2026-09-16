import re
import urllib.parse
import requests
import feedparser
import trafilatura
import time
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
        # "WSJ": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", # 결과 뉴스들이 최신화가 안되어 있는 것으로 보임(구독 필요)
        "YahooFinance": "https://finance.yahoo.com/news/rssindex",
        "FT": "https://www.ft.com/?format=rss"
    }
    
    all_news = []
    now = datetime.now(timezone.utc)
    
    for source_name, url in rss_urls.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                # 💡 1. RSS 발행일(published_parsed) 파싱 및 48시간 날짜 필터링
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed), timezone.utc)
                    if now - pub_date > timedelta(hours=48):
                        continue # 이틀이 지난 과거 기사는 버림
                else:
                    pub_date = now # 날짜 정보가 없는 예외 케이스 처리

                raw_desc = entry.get('summary', '')
                clean_desc = re.sub(r'<.*?>', '', raw_desc)
                
                all_news.append({
                    "source": source_name,
                    "title": entry.title,
                    "description": clean_desc,
                    "link": entry.link,
                    "pub_date": pub_date
                })
        except Exception as e:
            print(f"❌ 해외 뉴스 수집 에러 ({source_name}): {e}")
            
    # 💡 2. 매체 구분 없이 수집된 전체 기사를 최신 시간순으로 통합 정렬
    all_news.sort(key=lambda x: x['pub_date'], reverse=True)
    
    # 💡 3. 정렬된 전체 리스트에서 목표 개수만큼만 잘라서 최종 반환
    final_news = []
    for idx, item in enumerate(all_news[:count]):
        final_news.append({
            "id": f"US_{item['source']}_{idx+1}",
            "source": item['source'],
            "title": item['title'],
            "description": item['description'],
            "link": item['link']
        })
        
    return final_news

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