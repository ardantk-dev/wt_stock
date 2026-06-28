import yfinance as yf
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import urllib.parse
import re
from datetime import datetime, timedelta

def get_kr_stock_name(code):
    """Fetches the official Korean stock name using Naver Finance."""
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            match = re.search(r'<title>(.*?) : Npay', r.text)
            if match:
                return match.group(1).strip()
    except Exception as e:
        print(f"Error fetching KR stock name for '{code}': {e}")
    return code

def search_naver_ticker(query):
    """
    Searches stock ticker using Naver Search.
    Returns (ticker, name) or (None, None)
    """
    query = query.strip()
    if not query:
        return None, None
        
    # If query is a 6-digit number, it's a ticker code
    if query.isdigit() and len(query) == 6:
        name = get_kr_stock_name(query)
        # Determine KS or KQ by testing on yfinance
        for suffix in [".KS", ".KQ"]:
            try:
                t = yf.Ticker(f"{query}{suffix}")
                hist = t.history(period="1d")
                if not hist.empty:
                    return f"{query}{suffix}", name
            except Exception:
                pass
        return f"{query}.KS", name

    # Otherwise, search by name using Naver Search
    url = f"https://search.naver.com/search.naver?query={urllib.parse.quote(query + ' 주가')}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            codes = re.findall(r'code=(\d{6})', r.text)
            if codes:
                code = codes[0]
                name = get_kr_stock_name(code)
                # Determine KOSPI (.KS) vs KOSDAQ (.KQ)
                for suffix in [".KS", ".KQ"]:
                    try:
                        t = yf.Ticker(f"{code}{suffix}")
                        hist = t.history(period="1d")
                        if not hist.empty:
                            return f"{code}{suffix}", name
                    except Exception:
                        pass
                return f"{code}.KS", name
    except Exception as e:
        print(f"Error searching Naver ticker for '{query}': {e}")
    return None, None

def resolve_ticker(name_or_symbol, nation="KR"):
    """
    Resolves a stock name or ticker symbol to a standard yfinance ticker.
    Returns (ticker_symbol, resolved_name) or (None, None) if not found.
    """
    name_or_symbol = name_or_symbol.strip()
    
    if nation.upper() == "KR":
        ticker, name = search_naver_ticker(name_or_symbol)
        if ticker:
            return ticker, name
        
        # Fallback for 6-digit numeric input
        clean_symbol = name_or_symbol.split(".")[0]
        if clean_symbol.isdigit() and len(clean_symbol) == 6:
            name = get_kr_stock_name(clean_symbol)
            return f"{clean_symbol}.KS", name
                
    else:  # US
        # US is typically ticker symbol (e.g. AAPL, TSLA)
        # Verify ticker validity with a quick check
        symbol = name_or_symbol.upper()
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="1d")
            if not hist.empty:
                # Retrieve official shortName if possible
                info = t.info
                name = info.get("shortName", symbol)
                return symbol, name
        except Exception:
            pass
        return symbol, symbol  # Fallback to symbol as name
        
    return None, None

def get_korean_news(stock_name, max_results=3):
    """Fetches recent news for a Korean stock using Google News RSS."""
    query = urllib.parse.quote(f"{stock_name} 주식")
    url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = []
            for item in root.findall('.//item')[:max_results]:
                title = item.find('title').text
                link = item.find('link').text
                # Remove publisher from title (usually ends with " - Publisher")
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                items.append({"title": title, "link": link})
            return items
    except Exception as e:
        print(f"Error fetching news for {stock_name}: {e}")
    return []

def get_us_news(ticker, max_results=3):
    """Fetches recent news for a US stock using yfinance or Google News RSS."""
    try:
        t = yf.Ticker(ticker)
        news = t.news
        if news:
            items = []
            for item in news[:max_results]:
                title = item.get("title")
                link = item.get("link")
                if title and link:
                    items.append({"title": title, "link": link})
            return items
    except Exception as e:
        print(f"Error fetching yfinance news for {ticker}: {e}")
    
    # Fallback to Google News RSS
    query = urllib.parse.quote(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = []
            for item in root.findall('.//item')[:max_results]:
                title = item.find('title').text
                link = item.find('link').text
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                items.append({"title": title, "link": link})
            return items
    except Exception:
        pass
    return []

def calculate_rsi(prices, period=14):
    """Calculates the Relative Strength Index (RSI) for a pandas Series of prices."""
    if len(prices) < period + 1:
        return None
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def get_stock_summary(ticker, nation="KR"):
    """
    Fetches detailed stock information: current price, change,
    20-day moving average, RSI, daily range, and recent news.
    """
    try:
        t = yf.Ticker(ticker)
        # Fetch 30 days to calculate 20 MA and 14 RSI
        hist = t.history(period="45d")
        if hist.empty:
            return None
        
        latest = hist.iloc[-1]
        close_price = latest['Close']
        high_price = latest['High']
        low_price = latest['Low']
        
        # Calculate percentage change
        if len(hist) >= 2:
            prev_close = hist.iloc[-2]['Close']
            change = close_price - prev_close
            pct_change = (change / prev_close) * 100
        else:
            prev_close = close_price
            change = 0.0
            pct_change = 0.0
            
        # Moving averages
        ma_20 = hist['Close'].rolling(window=20).mean().iloc[-1] if len(hist) >= 20 else None
        
        # RSI
        rsi_14 = calculate_rsi(hist['Close'], period=14) if len(hist) >= 15 else None
        
        # Resolve official name
        name = ticker
        if nation.upper() == "KR":
            _, resolved_name = search_naver_ticker(ticker.split(".")[0])
            if resolved_name:
                name = resolved_name
        else:
            try:
                name = t.info.get("shortName", ticker)
            except Exception:
                pass
                
        # News
        news = get_korean_news(name, 2) if nation.upper() == "KR" else get_us_news(ticker, 2)
        
        return {
            "ticker": ticker,
            "name": name,
            "close": close_price,
            "change": change,
            "pct_change": pct_change,
            "high": high_price,
            "low": low_price,
            "ma_20": ma_20,
            "rsi_14": rsi_14,
            "news": news
        }
    except Exception as e:
        print(f"Error summarising stock {ticker}: {e}")
        return None

def fetch_market_indices():
    """Fetches status of domestic & international market indices, futures, yields."""
    indices = {
        # US Market
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Dow Jones": "^DJI",
        # US Futures
        "S&P 500 Futures": "ES=F",
        "Nasdaq 100 Futures": "NQ=F",
        # KR Market
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        # Macro Indicators
        "US 10Y Yield": "^TNX",
        "USD/KRW": "USDKRW=X"
    }
    
    results = {}
    for name, ticker in indices.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                close = hist.iloc[-1]['Close']
                if len(hist) >= 2:
                    prev_close = hist.iloc[-2]['Close']
                else:
                    prev_close = close
                change = close - prev_close
                pct_change = (change / prev_close) * 100
                results[name] = {
                    "close": close,
                    "change": change,
                    "pct_change": pct_change
                }
            else:
                results[name] = None
        except Exception as e:
            print(f"Error fetching index {name} ({ticker}): {e}")
            results[name] = None
            
    return results

def format_morning_briefing(portfolio_data):
    """
    Generates the morning briefing text (7:00 AM KST).
    Includes US market recap, futures, bond yields, exchange rate,
    owned stocks' analysis, and news.
    """
    indices = fetch_market_indices()
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    brief = f"🌅 *[아침 모닝 브리핑]* - {now_str}\n\n"
    
    # 1. US Market Recap
    brief += "📊 *미국 증시 마감 현황*\n"
    for name in ["S&P 500", "Nasdaq", "Dow Jones"]:
        data = indices.get(name)
        if data:
            sign = "🔺" if data['change'] > 0 else "🔻" if data['change'] < 0 else "➖"
            brief += f"• {name}: {data['close']:,.2f} ({sign} {data['pct_change']:.2f}%)\n"
        else:
            brief += f"• {name}: 정보 없음\n"
    brief += "\n"
    
    # 2. Futures & Macro Indicators
    brief += "🌐 *글로벌 야간 선물 및 매크로 지표*\n"
    for name in ["S&P 500 Futures", "Nasdaq 100 Futures"]:
        data = indices.get(name)
        if data:
            sign = "🔺" if data['change'] > 0 else "🔻" if data['change'] < 0 else "➖"
            brief += f"• {name}: {data['close']:,.2f} ({sign} {data['pct_change']:.2f}%)\n"
            
    yield_data = indices.get("US 10Y Yield")
    if yield_data:
        sign = "🔺" if yield_data['change'] > 0 else "🔻" if yield_data['change'] < 0 else "➖"
        brief += f"• 미국채 10년 금리: {yield_data['close']:.3f}% ({sign} {yield_data['pct_change']:.2f}%)\n"
        
    ex_data = indices.get("USD/KRW")
    if ex_data:
        sign = "🔺" if ex_data['change'] > 0 else "🔻" if ex_data['change'] < 0 else "➖"
        brief += f"• 원/달러 환율: {ex_data['close']:,.2f}원 ({sign} {ex_data['pct_change']:.2f}%)\n"
    brief += "\n"
    
    # 3. Owned Stocks Analysis
    brief += "💼 *보유 종목 분석 및 진단*\n"
    
    all_stocks = []
    for stock in portfolio_data.get("KR", []):
        all_stocks.append((stock, "KR"))
    for stock in portfolio_data.get("US", []):
        all_stocks.append((stock, "US"))
        
    if not all_stocks:
        brief += "_등록된 보유 종목이 없습니다._\n\n"
    else:
        news_items = []
        for stock_info, nation in all_stocks:
            ticker = stock_info["ticker"]
            buy_price = stock_info["buy_price"]
            qty = stock_info["quantity"]
            
            data = get_stock_summary(ticker, nation)
            if data:
                # Calculate profit / loss
                close = data["close"]
                pct_change = data["pct_change"]
                profit_pct = ((close - buy_price) / buy_price) * 100
                total_val = close * qty
                total_profit = (close - buy_price) * qty
                
                sign = "🔺" if pct_change > 0 else "🔻" if pct_change < 0 else "➖"
                profit_sign = "+" if profit_pct > 0 else ""
                
                brief += f"• *{data['name']}* ({ticker})\n"
                curr_symbol = "원" if nation == "KR" else "$"
                brief += f"  - 현재가: {close:,.2f}{curr_symbol} ({sign} {pct_change:.2f}%)\n"
                brief += f"  - 평가수익률: {profit_sign}{profit_pct:.2f}% (평가손익: {total_profit:+,.2f}{curr_symbol})\n"
                
                # Technical highlights
                if data["ma_20"]:
                    pos = "위 🟢" if close > data["ma_20"] else "아래 🔴"
                    brief += f"  - 20일 이평선: 대비 {pos}\n"
                if data["rsi_14"]:
                    rsi_status = "과매수 ⚠️" if data["rsi_14"] > 70 else "과매도 ⚡" if data["rsi_14"] < 30 else "보통"
                    brief += f"  - RSI (14): {data['rsi_14']:.1f} ({rsi_status})\n"
                
                # Add news to the collector
                if data["news"]:
                    news_items.append((data["name"], data["news"]))
            else:
                brief += f"• *{stock_info['name']}* ({ticker}): 데이터 로드 실패\n"
        
        brief += "\n"
        
        # 4. News Section
        if news_items:
            brief += "📰 *보유 종목 관련 최신 뉴스*\n"
            for name, articles in news_items:
                brief += f"• *{name}*\n"
                for art in articles:
                    brief += f"  - [{art['title']}]({art['link']})\n"
            brief += "\n"
            
    brief += "💡 오늘 하루도 성공 투자 하세요! 🚀"
    return brief

def format_evening_briefing(portfolio_data):
    """
    Generates the evening briefing text (8:30 PM KST).
    Includes KR market close recap, portfolio valuation summary,
    and a prompt to update trading logs.
    """
    indices = fetch_market_indices()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    brief = f"🌆 *[저녁 마감 브리핑]* - {now_str}\n\n"
    
    # 1. KR Market Recap
    brief += "📊 *국내 증시 마감 현황*\n"
    for name in ["KOSPI", "KOSDAQ"]:
        data = indices.get(name)
        if data:
            sign = "🔺" if data['change'] > 0 else "🔻" if data['change'] < 0 else "➖"
            brief += f"• {name}: {data['close']:,.2f} ({sign} {data['pct_change']:.2f}%)\n"
        else:
            brief += f"• {name}: 정보 없음\n"
    brief += "\n"
    
    # 2. Portfolio Valuation Summary
    brief += "💼 *보유 포트폴리오 마감 현황*\n"
    
    all_stocks = []
    for stock in portfolio_data.get("KR", []):
        all_stocks.append((stock, "KR"))
    for stock in portfolio_data.get("US", []):
        all_stocks.append((stock, "US"))
        
    if not all_stocks:
        brief += "_등록된 보유 종목이 없습니다._\n\n"
    else:
        total_kr_buy = 0
        total_kr_eval = 0
        total_us_buy = 0
        total_us_eval = 0
        
        # Get USD/KRW exchange rate to show a consolidated value if possible
        ex_rate = 1350.0 # fallback
        ex_data = indices.get("USD/KRW")
        if ex_data:
            ex_rate = ex_data["close"]
            
        brief_items = []
        for stock_info, nation in all_stocks:
            ticker = stock_info["ticker"]
            buy_price = stock_info["buy_price"]
            qty = stock_info["quantity"]
            
            data = get_stock_summary(ticker, nation)
            if data:
                close = data["close"]
                pct_change = data["pct_change"]
                profit_pct = ((close - buy_price) / buy_price) * 100
                total_profit = (close - buy_price) * qty
                
                sign = "🔺" if pct_change > 0 else "🔻" if pct_change < 0 else "➖"
                profit_sign = "+" if profit_pct > 0 else ""
                curr_symbol = "원" if nation == "KR" else "$"
                
                if nation == "KR":
                    total_kr_buy += buy_price * qty
                    total_kr_eval += close * qty
                else:
                    total_us_buy += buy_price * qty
                    total_us_eval += close * qty
                    
                brief_items.append(
                    f"• *{data['name']}*: {close:,.2f}{curr_symbol} ({sign} {pct_change:.2f}%) | 수익률: {profit_sign}{profit_pct:.2f}%"
                )
            else:
                brief_items.append(f"• *{stock_info['name']}* ({ticker}): 데이터 로드 실패")
                
        for item in brief_items:
            brief += f"{item}\n"
        brief += "\n"
        
        # Consolidated Summary
        brief += "📊 *포트폴리오 자산 요약*\n"
        if total_kr_buy > 0:
            kr_profit_pct = ((total_kr_eval - total_kr_buy) / total_kr_buy) * 100
            kr_sign = "+" if kr_profit_pct > 0 else ""
            brief += f"• 국내 주식 평가액: {total_kr_eval:,.0f}원 ({kr_sign}{kr_profit_pct:.2f}%, 수익: {total_kr_eval - total_kr_buy:+,.0f}원)\n"
        if total_us_buy > 0:
            us_profit_pct = ((total_us_eval - total_us_buy) / total_us_buy) * 100
            us_sign = "+" if us_profit_pct > 0 else ""
            brief += f"• 해외 주식 평가액: {total_us_eval:,.2f}$ ({us_sign}{us_profit_pct:.2f}%, 수익: {total_us_eval - total_us_buy:+,.2f}$)\n"
            
        # Grand total in KRW
        grand_buy_krw = total_kr_buy + (total_us_buy * ex_rate)
        grand_eval_krw = total_kr_eval + (total_us_eval * ex_rate)
        if grand_buy_krw > 0:
            grand_profit_pct = ((grand_eval_krw - grand_buy_krw) / grand_buy_krw) * 100
            grand_sign = "+" if grand_profit_pct > 0 else ""
            brief += f"• *총 평가 자산 (원화 환산)*: {grand_eval_krw:,.0f}원 ({grand_sign}{grand_profit_pct:.2f}%, 수익: {grand_eval_krw - grand_buy_krw:+,.0f}원)\n"
        brief += "\n"
        
    brief += "✍️ *오늘의 매매 기록 업데이트*\n"
    brief += "오늘 거래하신 매매 기록이 있다면 지금 등록해 보세요!\n"
    brief += "채팅창에 아래 양식으로 입력하면 즉시 반영됩니다:\n"
    brief += "`[종목명 또는 코드] 매수/매도 [수량] [단가]`\n"
    brief += "*(예: 삼성전자 매수 10 75000)*\n"
    brief += "*(예: AAPL 매도 5 185)*\n\n"
    brief += "또는 아래 메뉴 버튼을 이용해 포트폴리오를 조회해보세요. 👇"
    
    return brief
