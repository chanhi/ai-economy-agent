import requests
import yfinance as yf
import csv
import time
from datetime import datetime, timedelta
from config import ALPHA_VANTAGE_API_KEY, TARGET_EARNINGS_SYMBOLS, TOP_MOVERS_LIMIT

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

def fetch_major_earnings_schedule():
    url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey={ALPHA_VANTAGE_API_KEY}"
    upcoming_earnings = []
    
    try:
        with requests.Session() as s:
            download = s.get(url)
            download.raise_for_status()
            
            decoded_content = download.content.decode('utf-8')
            
            # 💡 API 한도 방어
            if "Information" in decoded_content or "Rate Limit" in decoded_content or "{" in decoded_content:
                return "일정 데이터 수집 불가 (API 한도 초과)"

            csv_reader = csv.DictReader(decoded_content.splitlines(), delimiter=',')
            today = datetime.now().date()
            end_date = today + timedelta(days=7)
            
            for row in csv_reader:
                try:
                    report_date = datetime.strptime(row['reportDate'], '%Y-%m-%d').date()
                    symbol = row['symbol']
                    
                    if today <= report_date <= end_date and symbol in TARGET_EARNINGS_SYMBOLS:
                        upcoming_earnings.append(f"- {report_date} : {symbol} ({row['name']}) 실적 발표")
                except Exception:
                    continue
                    
    except Exception as e:
        print(f"❌ 실적 캘린더 수집 에러: {e}")
        return "실적 일정 데이터를 불러오지 못했습니다."
        
    if upcoming_earnings:
        return "\n".join(upcoming_earnings)
    else:
        return "이번 주 예정된 주요 빅테크(M7 등) 실적 발표 없음."

def fetch_top_movers():
    # 💡 동시 호출 방어: 앞선 실적 API와 충돌 방지를 위해 3초 대기
    time.sleep(3)
    
    url = f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={ALPHA_VANTAGE_API_KEY}"
    
    try:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        
        # 💡 API 한도 초과 방어
        if "Information" in data or "Rate Limit" in data:
            print("⚠️ Alpha Vantage API 한도 초과입니다.")
            return "주도주 데이터 수집 불가 (API 한도 초과)"
            
        def format_stocks(stock_list, count=TOP_MOVERS_LIMIT):
            if not stock_list: 
                return "데이터 없음"
            result = []
            for stock in stock_list[:count]:
                ticker = stock.get('ticker', '')
                change_pct = stock.get('change_percentage', '')
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