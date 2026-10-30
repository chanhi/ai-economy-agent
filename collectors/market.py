import csv
import time
from datetime import datetime, timedelta

import requests
import yfinance as yf
from config import ALPHA_VANTAGE_API_KEY, TARGET_EARNINGS_SYMBOLS, TOP_MOVERS_LIMIT

MACRO_TICKERS = [
    ("S&P 500", "^GSPC", "index"),
    ("나스닥", "^IXIC", "index"),
    ("코스피", "^KS11", "index"),
    ("원/달러 환율", "KRW=X", "krw"),
    ("미국 10년물 국채금리", "^TNX", "yield"),
    ("VIX 변동성 지수", "^VIX", "vix"),
    ("WTI 원유", "CL=F", "usd"),
    ("국제 금", "GC=F", "usd"),
]


def _format_level(val: float, fmt_type: str) -> str:
    if fmt_type == "krw":
        return f"{val:,.2f}원"
    if fmt_type == "yield":
        return f"{val:.3f}%"
    if fmt_type == "usd":
        return f"${val:,.2f}"
    return f"{val:,.2f}"


def fetch_macro_snapshot() -> tuple[str, dict]:
    """
    8대 핵심 거시 지표의 현재가 + 전일 대비(1D) + 5거래일(5D) 등락률을 계산하여
    프롬프트 주입용 요약 문자열과 DB/API 저장용 구조화 딕셔너리를 함께 반환합니다.
    """
    summary_parts = []
    structured = {}
    print("\n📈 실시간 거시 경제 지표(등락률 포함)를 수집 중입니다...")

    for name, ticker, fmt_type in MACRO_TICKERS:
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="7d")
            closes = hist["Close"].dropna() if not hist.empty and "Close" in hist else []

            if len(closes) >= 1:
                latest = float(closes.iloc[-1])
                level_str = _format_level(latest, fmt_type)

                change_1d_pct = None
                change_5d_pct = None
                delta_str = ""

                if len(closes) >= 2 and closes.iloc[-2] != 0:
                    prev = float(closes.iloc[-2])
                    change_1d_pct = round(((latest - prev) / abs(prev)) * 100, 2)
                    if fmt_type == "yield":
                        bp_diff = round((latest - prev) * 100, 1)
                        delta_str = f" ({bp_diff:+.1f}bp"
                    else:
                        delta_str = f" ({change_1d_pct:+.2f}%"

                    if len(closes) >= 5 and closes.iloc[-5] != 0:
                        prev5 = float(closes.iloc[-5])
                        change_5d_pct = round(((latest - prev5) / abs(prev5)) * 100, 2)
                        delta_str += f", 5일 {change_5d_pct:+.2f}%)"
                    else:
                        delta_str += ")"

                summary_parts.append(f"{name}: {level_str}{delta_str}")
                structured[name] = {
                    "ticker": ticker,
                    "value": round(latest, 4),
                    "display": f"{level_str}{delta_str}",
                    "change_1d_pct": change_1d_pct,
                    "change_5d_pct": change_5d_pct,
                }
            else:
                summary_parts.append(f"{name}: 데이터 없음")
        except Exception as e:
            print(f"  ❌ {name} 지표 수집 에러: {e}")
            summary_parts.append(f"{name}: 조회 실패")

    indicator_string = " | ".join(summary_parts)
    print(f"  ✅ 수집 완료: {indicator_string}")
    return indicator_string, structured


def fetch_macro_indicators() -> str:
    """하위 호환용 문자열 반환 래퍼"""
    indicator_string, _ = fetch_macro_snapshot()
    return indicator_string


def fetch_major_earnings_schedule() -> str:
    if not ALPHA_VANTAGE_API_KEY:
        return "실적 일정 미설정 (API 키 없음)"

    url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey={ALPHA_VANTAGE_API_KEY}"
    upcoming_earnings = []

    try:
        with requests.Session() as s:
            download = s.get(url, timeout=12)
            download.raise_for_status()
            decoded_content = download.content.decode("utf-8")

            if "Information" in decoded_content or "Rate Limit" in decoded_content or "{" in decoded_content:
                return "일정 데이터 수집 불가 (API 한도 초과)"

            csv_reader = csv.DictReader(decoded_content.splitlines(), delimiter=",")
            today = datetime.now().date()
            end_date = today + timedelta(days=7)

            for row in csv_reader:
                try:
                    report_date = datetime.strptime(row["reportDate"], "%Y-%m-%d").date()
                    symbol = row["symbol"]
                    if today <= report_date <= end_date and symbol in TARGET_EARNINGS_SYMBOLS:
                        upcoming_earnings.append(f"- {report_date} : {symbol} ({row['name']}) 실적 발표")
                except Exception:
                    continue
    except Exception as e:
        print(f"❌ 실적 캘린더 수집 에러: {e}")
        return "실적 일정 데이터를 불러오지 못했습니다."

    return "\n".join(upcoming_earnings) if upcoming_earnings else "이번 주 예정된 주요 빅테크(M7 등) 실적 발표 없음."


def fetch_top_movers() -> str:
    if not ALPHA_VANTAGE_API_KEY:
        return "주도주 미설정 (API 키 없음)"

    time.sleep(2)
    url = f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={ALPHA_VANTAGE_API_KEY}"

    try:
        res = requests.get(url, timeout=12)
        res.raise_for_status()
        data = res.json()

        if "Information" in data or "Rate Limit" in data:
            return "주도주 데이터 수집 불가 (API 한도 초과)"

        def format_stocks(stock_list, count=TOP_MOVERS_LIMIT):
            if not stock_list:
                return "데이터 없음"
            return ", ".join(
                f"{s.get('ticker', '')} ({s.get('change_percentage', '')})"
                for s in stock_list[:count]
            )

        return (
            f"- 🚀 급등주 (Top Gainers): {format_stocks(data.get('top_gainers', []))}\n"
            f"- 📉 급락주 (Top Losers): {format_stocks(data.get('top_losers', []))}\n"
            f"- 🔥 거래량 상위 (Most Active): {format_stocks(data.get('most_actively_traded', []))}"
        )
    except Exception as e:
        print(f"❌ 주도주 수집 에러: {e}")
        return "시장 주도주 데이터를 불러오지 못했습니다."
