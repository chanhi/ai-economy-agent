import hashlib
import html
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
import trafilatura
from config import NCP_CLIENT_ID, NCP_CLIENT_SECRET

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# 하드 페이월 또는 안티봇으로 본문 추출이 항상 막히는 도메인은 즉시 스킵하여 불필요한 지연 차단
SKIP_BODY_DOMAINS = (
    "ft.com",
    "marketwatch.com",
    "investing.com",
    "wsj.com",
    "bloomberg.com",
    "barrons.com",
)


def make_article_id(prefix: str, link: str) -> str:
    """URL 해시 기반 결정론적 고유 ID 생성 (시간당 배치 간 KR_1 중복 충돌 원천 방지)"""
    digest = hashlib.sha1(link.strip().encode("utf-8")).hexdigest()[:10]
    safe_prefix = re.sub(r"[^A-Za-z0-9_]", "", prefix)
    return f"{safe_prefix}_{digest}"


def _clean_html_snippet(raw_text: str) -> str:
    text = re.sub(r"<.*?>", "", raw_text or "")
    return html.unescape(text).strip()


def fetch_domestic_news(keyword: str, count: int = 10) -> list[dict]:
    encoded_query = urllib.parse.quote(keyword)
    api_url = f"https://naverapihub.apigw.ntruss.com/search/v1/news?query={encoded_query}&display=50&sort=sim"

    headers = {
        "X-NCP-APIGW-API-KEY-ID": NCP_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NCP_CLIENT_SECRET,
    }

    news_list = []
    seen_links = set()
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        items = response.json().get("items", [])

        now = datetime.now(timezone.utc)

        for item in items:
            pub_date = parsedate_to_datetime(item["pubDate"])
            if now - pub_date > timedelta(hours=24):
                continue

            link = (item.get("originallink") or item.get("link") or "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            title = _clean_html_snippet(item.get("title", ""))
            desc = _clean_html_snippet(item.get("description", ""))

            news_list.append({
                "id": make_article_id("KR", link),
                "source": "Naver",
                "title": title,
                "description": desc,
                "link": link,
                "pub_date": pub_date.isoformat(),
            })

            if len(news_list) >= count:
                break

    except Exception as e:
        print(f"❌ 네이버 뉴스 수집 에러 ({keyword}): {e}")

    return news_list


def fetch_overseas_news(count: int = 50) -> list[dict]:
    rss_urls = {
        "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "CNBC_Econ": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
        "Fed": "https://www.federalreserve.gov/feeds/press_all.xml",
        "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "Investing": "https://www.investing.com/rss/news.rss",
        "FT": "https://www.ft.com/?format=rss",
    }

    all_news = []
    seen_links = set()
    now = datetime.now(timezone.utc)

    for source_name, url in rss_urls.items():
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                link = (getattr(entry, "link", "") or "").strip()
                if not link or link in seen_links:
                    continue

                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed), timezone.utc)
                    if now - pub_date > timedelta(hours=48):
                        continue
                else:
                    pub_date = now

                seen_links.add(link)
                clean_title = _clean_html_snippet(getattr(entry, "title", ""))
                clean_desc = _clean_html_snippet(entry.get("summary", ""))

                all_news.append({
                    "source": source_name,
                    "title": clean_title,
                    "description": clean_desc,
                    "link": link,
                    "pub_date": pub_date,
                })
        except Exception as e:
            print(f"❌ 해외 뉴스 수집 에러 ({source_name}): {e}")

    all_news.sort(key=lambda x: x["pub_date"], reverse=True)

    final_news = []
    for item in all_news[:count]:
        final_news.append({
            "id": make_article_id(f"US_{item['source']}", item["link"]),
            "source": item["source"],
            "title": item["title"],
            "description": item["description"],
            "link": item["link"],
            "pub_date": item["pub_date"].isoformat(),
        })

    return final_news


def fetch_article_text(url: str, min_chars: int = 200, max_chars: int = 6000) -> str:
    """
    기사 원문 URL에서 본문만 정밀 추출합니다.
    - 페이월 도메인은 즉시 빈 문자열을 반환해 지연 시간을 방지합니다.
    - raw bytes(response.content)를 trafilatura에 전달하여 국내 언론사 인코딩 깨짐을 방지합니다.
    """
    if not url:
        return ""

    parsed_host = urllib.parse.urlparse(url).netloc.lower()
    if any(domain in parsed_host for domain in SKIP_BODY_DOMAINS):
        return ""

    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        if response.status_code == 200 and response.content:
            text = trafilatura.extract(
                response.content,
                favor_precision=True,
                include_comments=False,
                include_tables=False,
            )
            if text and len(text.strip()) >= min_chars:
                return text.strip()[:max_chars]
    except Exception as e:
        print(f"  ⚠️ 본문 추출 스킵 ({parsed_host}): {e}")
    return ""
