import yfinance as yf
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import urllib.parse
import re
from datetime import datetime, timedelta
import os
import json
from google import genai

def get_kr_stock_name(code):
    """Fetches the official Korean stock name using Naver Finance."""
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=5)
        r.encoding = r.apparent_encoding
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
        r.encoding = r.apparent_encoding
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
    20-day moving average, 60-day moving average, RSI, daily range, and recent news.
    """
    try:
        t = yf.Ticker(ticker)
        # Fetch 90 days to calculate 60 MA, 20 MA and 14 RSI
        hist = t.history(period="90d")
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
        ma_60 = hist['Close'].rolling(window=60).mean().iloc[-1] if len(hist) >= 60 else None
        
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
            "ma_60": ma_60,
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

def generate_stock_strategies(portfolio_data, api_key):
    """
    Calls Gemini API to generate a short trading strategy (under 100 characters)
    for each stock in the portfolio, based on technical indicators and news.
    Returns a dictionary mapping ticker to strategy string.
    """
    if not api_key:
        return {}
        
    try:
        client = genai.Client(api_key=api_key)
        
        all_stocks = []
        for stock in portfolio_data.get("KR", []):
            all_stocks.append((stock, "KR"))
        for stock in portfolio_data.get("US", []):
            all_stocks.append((stock, "US"))
            
        if not all_stocks:
            return {}
            
        stocks_info = []
        for stock_info, nation in all_stocks:
            ticker = stock_info["ticker"]
            buy_price = stock_info["buy_price"]
            qty = stock_info["quantity"]
            
            data = get_stock_summary(ticker, nation)
            if data:
                close = data["close"]
                pct_change = data["pct_change"]
                profit_pct = ((close - buy_price) / buy_price) * 100
                news_titles = [n['title'] for n in data['news']] if data['news'] else []
                
                stocks_info.append({
                    "ticker": ticker,
                    "name": data["name"],
                    "nation": nation,
                    "close": close,
                    "buy_price": buy_price,
                    "profit_pct": profit_pct,
                    "ma_20": data["ma_20"],
                    "ma_60": data["ma_60"],
                    "rsi_14": data["rsi_14"],
                    "news": news_titles
                })
                
        if not stocks_info:
            return {}
            
        prompt = f"""
당신은 전문 주식 분석가입니다. 아래 제공되는 각 종목의 기술적 지표와 뉴스 정보를 바탕으로, 오늘 하루 어떻게 대응해야 하는지 '당일 매매 전략'을 종목당 100자 이내의 아주 명확하고 간결한 한국어로 작성해 주세요.

응답 형식은 반드시 JSON 형태여야 하며, 키는 각 종목의 티커(예: '005930.KS')이고, 값은 100자 이내의 당일 매매 전략 문자열이어야 합니다. 마크다운 코드 블록(```json ... ```)이나 기타 설명 텍스트를 포함하지 말고 오직 순수한 JSON 문자열만 응답으로 돌려주십시오.

종목 정보:
{json.dumps(stocks_info, ensure_ascii=False, indent=2)}
"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            
        return json.loads(text)
    except Exception as e:
        print(f"Error generating stock strategies with Gemini: {e}")
        return {}

def generate_noon_strategies(portfolio_data, indices_data, api_key):
    """
    Calls Gemini API to generate Buy/Hold/Sell percentages and a short afternoon trading strategy (under 50 characters)
    for each stock in the portfolio, based on macro indices and morning price movements and indicators.
    Returns a dictionary mapping ticker to a dict containing buy, hold, sell, and strategy.
    """
    if not api_key:
        return {}
        
    try:
        client = genai.Client(api_key=api_key)
        
        all_stocks = []
        for stock in portfolio_data.get("KR", []):
            all_stocks.append((stock, "KR"))
        for stock in portfolio_data.get("US", []):
            all_stocks.append((stock, "US"))
            
        if not all_stocks:
            return {}
            
        stocks_info = []
        for stock_info, nation in all_stocks:
            ticker = stock_info["ticker"]
            buy_price = stock_info["buy_price"]
            qty = stock_info["quantity"]
            
            data = get_stock_summary(ticker, nation)
            if data:
                close = data["close"]
                pct_change = data["pct_change"]
                profit_pct = ((close - buy_price) / buy_price) * 100
                news_titles = [n['title'] for n in data['news']] if data['news'] else []
                
                stocks_info.append({
                    "ticker": ticker,
                    "name": data["name"],
                    "nation": nation,
                    "close": close,
                    "buy_price": buy_price,
                    "profit_pct": profit_pct,
                    "ma_20": data["ma_20"],
                    "ma_60": data["ma_60"],
                    "rsi_14": data["rsi_14"],
                    "news": news_titles
                })
                
        if not stocks_info:
            return {}
            
        prompt = f"""
당신은 전문 주식 분석가입니다. 오늘 오전의 거시 경제 흐름(미국 증시 결과, 금리, 환율 등)과 각 보유 종목들의 당일 오전장 가격 흐름(현재가, 전일대비 등락률, 이평선 위치, 최신 뉴스)을 모두 융합하여 오늘 오후장 대응을 분석하고 다음 두 가지 정보를 생성해 주세요.

1. 오후장 행동 추천 강도 (매수, 유지, 매도)를 각각 퍼센티지 정수형 수치로 환산해 주세요. (예: 매수 60%, 유지 30%, 매도 10%). 이 세 비율의 합은 반드시 정확히 100이어야 합니다. 거시 시황과 개별 종목의 오전장 가격 등락률, 차트 위치, 최신 뉴스를 유기적으로 모두 반영해야 합니다.
2. 50자 이내의 아주 간결하고 직관적인 오후장 매매 추천 전략 한글 텍스트.

응답 형식은 반드시 JSON 형태여야 하며, 키는 각 종목의 티커(예: '005930.KS')이고, 값은 다음 스키마를 따르는 객체여야 합니다. 마크다운 코드 블록(```json ... ```)이나 기타 설명 텍스트를 포함하지 말고 오직 순수한 JSON 문자열만 응답으로 돌려주십시오.

응답 JSON 스키마 예시:
{{
  "005930.KS": {{
    "buy": 60,
    "hold": 30,
    "sell": 10,
    "strategy": "50자 이내의 매매 추천 전략"
  }}
}}

[글로벌 거시 경제 및 시장 지표 정보]:
{json.dumps(indices_data, ensure_ascii=False, indent=2)}

[보유 종목 오전장 등락 및 지표 정보]:
{json.dumps(stocks_info, ensure_ascii=False, indent=2)}
"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            
        return json.loads(text)
    except Exception as e:
        print(f"Error generating noon stock strategies with Gemini: {e}")
        return {}

def format_noon_briefing(portfolio_data):
    """
    Generates the noon briefing text (12:00 PM KST).
    Includes owned stocks' morning price movements, technical summaries,
    and 50-character afternoon trading strategies.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    brief = f"🕛 *[정오 시황 및 포트폴리오 브리핑]* - {now_str}\n\n"
    brief += "📊 *오전장 보유 종목 등락 현황*\n"
    
    all_stocks = []
    for stock in portfolio_data.get("KR", []):
        all_stocks.append((stock, "KR"))
    for stock in portfolio_data.get("US", []):
        all_stocks.append((stock, "US"))
        
    if not all_stocks:
        brief += "_등록된 보유 종목이 없습니다._\n\n"
        return brief
        
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    api_key = ""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                api_key = cfg.get("gemini_api_key", "")
        except Exception as e:
            print(f"Error reading config for Gemini API key: {e}")
            
    strategies = {}
    if api_key:
        print("StockAnalyzer: Generating noon stock trading strategies with Gemini...")
        indices = fetch_market_indices()
        strategies = generate_noon_strategies(portfolio_data, indices, api_key)
        
    for stock_info, nation in all_stocks:
        ticker = stock_info["ticker"]
        buy_price = stock_info["buy_price"]
        qty = stock_info["quantity"]
        
        data = get_stock_summary(ticker, nation)
        if data:
            close = data["close"]
            pct_change = data["pct_change"]
            profit_pct = ((close - buy_price) / buy_price) * 100
            
            sign = "🔺" if pct_change > 0 else "🔻" if pct_change < 0 else "➖"
            profit_sign = "+" if profit_pct > 0 else ""
            
            brief += f"• *{data['name']}* ({ticker})\n"
            curr_symbol = "원" if nation == "KR" else "$"
            brief += f"  - 현재가: {close:,.2f}{curr_symbol} ({sign} {pct_change:.2f}%)\n"
            brief += f"  - 평가수익률: {profit_sign}{profit_pct:.2f}%\n"
            
            # Technical highlights
            techs = []
            if data["ma_20"]:
                pos_20 = "위 🟢" if close > data["ma_20"] else "아래 🔴"
                techs.append(f"20일 대비: {pos_20}")
            if data["ma_60"]:
                pos_60 = "위 🟢" if close > data["ma_60"] else "아래 🔴"
                techs.append(f"60일 대비: {pos_60}")
            if techs:
                brief += f"  - 기술적 분석: {' | '.join(techs)}\n"
                
            # Add afternoon strategy if generated
            # Fuzzy matching: check full ticker, numeric code, and company name
            strat_info = None
            for key_candidate in [ticker, ticker.split('.')[0], data['name']]:
                if key_candidate in strategies:
                    strat_info = strategies[key_candidate]
                    break
                    
            if strat_info:
                if isinstance(strat_info, dict):
                    buy_val = strat_info.get("buy", 0)
                    hold_val = strat_info.get("hold", 0)
                    sell_val = strat_info.get("sell", 0)
                    strat_text = strat_info.get("strategy", "")
                    
                    brief += f"  - 오후장 추천: 매수 {buy_val}% | 유지 {hold_val}% | 매도 {sell_val}%\n"
                    if strat_text:
                        brief += f"  - 오후장 전략: {strat_text}\n"
                else:
                    brief += f"  - 오후장 전략: {strat_info}\n"
        else:
            brief += f"• *{stock_info['name']}* ({ticker}): 데이터 로드 실패\n"
            
    brief += "\n💡 오후장도 안전하고 현명한 투자 되세요! 📈"
    return brief

def generate_ai_analysis(portfolio_data, indices_data, api_key):
    """
    Calls Gemini API to analyze the market and portfolio, and generate
    market recap, owned stocks proposals, and 3 new stock recommendations.
    """
    try:
        # Create genai client with api_key
        client = genai.Client(api_key=api_key)
        
        # Prepare market data string
        market_str = ""
        for name, data in indices_data.items():
            if data:
                market_str += f"- {name}: {data['close']:,.2f} (전일대비 {data['pct_change']:.2f}%)\n"
            else:
                market_str += f"- {name}: 데이터 없음\n"
                
        # Prepare portfolio data string
        portfolio_str = ""
        all_stocks = []
        for stock in portfolio_data.get("KR", []):
            all_stocks.append((stock, "KR"))
        for stock in portfolio_data.get("US", []):
            all_stocks.append((stock, "US"))
            
        if not all_stocks:
            portfolio_str = "보유 종목 없음\n"
        else:
            for stock_info, nation in all_stocks:
                ticker = stock_info["ticker"]
                buy_price = stock_info["buy_price"]
                qty = stock_info["quantity"]
                
                data = get_stock_summary(ticker, nation)
                if data:
                    close = data["close"]
                    pct_change = data["pct_change"]
                    profit_pct = ((close - buy_price) / buy_price) * 100
                    
                    portfolio_str += f"■ {data['name']} ({ticker}) [{nation}]\n"
                    portfolio_str += f"  - 평단가: {buy_price:,.2f} | 현재가: {close:,.2f} | 평가수익률: {profit_pct:+.2f}%\n"
                    if data["ma_20"]:
                        portfolio_str += f"  - 20일 이동평균선 대비: {'위 (상승세)' if close > data['ma_20'] else '아래 (하락세)'}\n"
                    if data["rsi_14"]:
                        portfolio_str += f"  - RSI (14): {data['rsi_14']:.1f}\n"
                    if data["news"]:
                        news_titles = [n['title'] for n in data['news']]
                        portfolio_str += f"  - 최근 관련 뉴스: {', '.join(news_titles)}\n"
                else:
                    portfolio_str += f"■ {stock_info['name']} ({ticker}) [{nation}]: 데이터 로드 실패\n"
                    
        # Construct prompt
        prompt = f"""
당신은 전문 주식 투자 분석가이자 자산관리 AI 에이전트입니다.
제시된 글로벌 시황 데이터와 사용자의 보유 종목 현황을 바탕으로, 오늘 아침 브리핑에 포함될 **글로벌 시황 분석**, **보유 종목 대응 제안**, 그리고 **오늘의 신규 종목 추천 3가지**를 작성해 주세요.

[글로벌 시황 데이터]
{market_str}

[사용자 보유 종목 현황]
{portfolio_str}

아래 작성 가이드를 엄격히 준수하여 텔레그램 메시지용 마크다운 형식으로 응답해 주세요.

[작성 가이드]
1. **글로벌 시황 분석**:
   - 전일 미국 증시(S&P 500, Nasdaq, Dow Jones)의 마감 특징과 야간 선물(S&P 500 Futures, Nasdaq 100 Futures)의 움직임을 요약해 주세요.
   - 미국채 10년물 금리와 원/달러 환율의 변동을 바탕으로, 오늘 한국 주식 시장(KOSPI, KOSDAQ)에 미칠 영향과 주요 투자 포인트를 2~3줄로 분석해 주세요.

2. **보유 종목 대응 제안 (3가지)**:
   - 사용자의 보유 종목 중 기술적 지표(RSI 과매수/과매도, 20일 이평선 돌파 여부)나 최근 뉴스, 수익률 상태를 고려하여 구체적이고 실천 가능한 대응 제안(매수/매도/홀딩 및 비중 조절 등)을 딱 3가지만 제안해 주세요.
   - 어떤 종목에 대한 제안인지 종목명과 티커를 명시해 주세요.

3. **오늘의 신규 종목 추천 (3가지)**:
   - 현재 시황(매크로 환경, 주도 섹터 등)에 적합한 국내(KR) 또는 미국(US) 주식 중에서 오늘 신규 진입을 고려해볼 만한 매력적인 종목 3가지를 추천해 주세요.
   - 각 종목별로 **종목명(티커)**와 **추천 이유(매수 논리)**를 명확하게 작성해 주세요.

응답은 마크다운 기호(`*`, `•`, `■`)를 적절히 활용하여 시각적으로 깔끔하고 읽기 쉽게 작성해 주시고, 인사말이나 마무리 말 없이 가이드의 1, 2, 3번 섹션만 바로 작성해 주세요.
"""

        # Generate content using the new SDK
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
            )
        except Exception as model_err:
            if "404" in str(model_err) or "NOT_FOUND" in str(model_err):
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=prompt,
                )
            else:
                raise model_err

        return response.text
    except Exception as e:
        print(f"Error generating AI analysis with Gemini: {e}")
        return ""


def format_morning_briefing(portfolio_data):
    """
    Generates the morning briefing text (7:00 AM KST).
    Includes US market recap, futures, bond yields, exchange rate,
    owned stocks' analysis, news, and optional Gemini AI analysis.
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
        # Load API key and generate stock strategies first if configured
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        api_key = ""
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    api_key = cfg.get("gemini_api_key", "")
            except Exception as e:
                print(f"Error reading config for Gemini API key: {e}")
                
        strategies = {}
        if api_key:
            print("StockAnalyzer: Generating individual stock trading strategies with Gemini...")
            strategies = generate_stock_strategies(portfolio_data, api_key)

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
                if data["ma_60"]:
                    pos_60 = "위 🟢" if close > data["ma_60"] else "아래 🔴"
                    brief += f"  - 60일 이평선: 대비 {pos_60}\n"
                if data["rsi_14"]:
                    rsi_status = "과매수 ⚠️" if data["rsi_14"] > 70 else "과매도 ⚡" if data["rsi_14"] < 30 else "보통"
                    brief += f"  - RSI (14): {data['rsi_14']:.1f} ({rsi_status})\n"
                
                # Add trading strategy if generated
                strat = strategies.get(ticker)
                if strat:
                    brief += f"  - 당일 매매 전략: {strat}\n"
                
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
            
    # 5. Gemini AI Market & Portfolio Analysis
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    api_key = ""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                api_key = cfg.get("gemini_api_key", "")
        except Exception as e:
            print(f"Error reading config for Gemini API key: {e}")
            
    if api_key:
        print("StockAnalyzer: Generating AI analysis with Gemini...")
        ai_analysis = generate_ai_analysis(portfolio_data, indices, api_key)
        if ai_analysis:
            brief += "\n🤖 *[Gemini AI 시장 분석 & 추천]*\n"
            brief += ai_analysis + "\n"
        else:
            print("StockAnalyzer: AI analysis generation returned empty result.")
    else:
        print("StockAnalyzer: Gemini API key is not configured. Skipping AI analysis.")

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

def analyze_single_stock_with_ai(query, api_key):
    """
    Analyzes a specific stock (KR or US) using Gemini AI.
    Returns formatted Markdown text for Telegram.
    """
    if not api_key:
        return "⚠️ *Gemini API 키 미설정*\n`config.json`에 `gemini_api_key`를 설정해 주세요."

    query = query.strip()
    if not query:
        return "⚠️ *종목명 또는 티커를 입력해 주세요.*\n(예: `/ai 삼성전자`, `/ai AAPL`, `/ai 005930`)"

    # Try resolving KR stock first
    ticker, name = resolve_ticker(query, nation="KR")
    nation = "KR"

    # If not resolved or fallback, try US
    if not ticker or (ticker.endswith(".KS") and name == query and not query.isdigit()):
        us_ticker, us_name = resolve_ticker(query, nation="US")
        if us_ticker and us_name != query:
            ticker, name, nation = us_ticker, us_name, "US"

    if not ticker:
        ticker, name, nation = query, query, "US"

    summary = get_stock_summary(ticker, nation)
    if not summary:
        # Fallback retry as US
        summary = get_stock_summary(query, "US")
        if summary:
            ticker, name, nation = query, summary.get("name", query), "US"

    if not summary:
        return f"❌ *'{query}' 종목 정보를 찾을 수 없습니다.*\n종목명이나 정확한 티커(코드)를 확인해 주세요."

    # Prepare data for Gemini
    price_str = f"{summary['close']:,.2f}{'원' if nation == 'KR' else '$'}"
    change_sign = "+" if summary['pct_change'] > 0 else ""
    pct_str = f"{change_sign}{summary['pct_change']:.2f}%"
    
    news_items = summary.get("news", [])
    news_titles = [n['title'] for n in news_items]
    news_str = "\n".join([f"- {t}" for t in news_titles]) if news_titles else "최근 헤드라인 뉴스 없음"

    tech_info = []
    if summary.get("ma_20"):
        pos_20 = "상승 우세 🟢" if summary['close'] > summary['ma_20'] else "하락 우세 🔴"
        tech_info.append(f"20일 이평선: {summary['ma_20']:,.2f} ({pos_20})")
    if summary.get("ma_60"):
        pos_60 = "상승 우세 🟢" if summary['close'] > summary['ma_60'] else "하락 우세 🔴"
        tech_info.append(f"60일 이평선: {summary['ma_60']:,.2f} ({pos_60})")
    if summary.get("rsi_14"):
        rsi_val = summary["rsi_14"]
        rsi_desc = "과매수 영역 ⚠️" if rsi_val > 70 else "과매도 영역 ⚡" if rsi_val < 30 else "중립 영역"
        tech_info.append(f"RSI (14): {rsi_val:.1f} ({rsi_desc})")

    tech_str = "\n".join([f"- {t}" for t in tech_info]) if tech_info else "기술적 지표 계산 중"

    prompt = f"""
당신은 최고 수준의 주식 투자 전략가 및 자산 관리 AI 에이전트입니다.
아래 제공된 특정 종목의 시세, 기술적 지표 및 최근 헤드라인 뉴스를 종합 분석하여 투자자를 위한 **1분 AI 종목 정밀 분석 리포트**를 작성해 주세요.

[분석 대상 종목]
- 종목명: {name} (티커: {ticker}, 국가: {nation})
- 현재가: {price_str} (전일대비: {pct_str})
- 주 52주 최고가: {summary.get('high_52', 0):,.2f} / 최저가: {summary.get('low_52', 0):,.2f}

[기술적 분석 지표]
{tech_str}

[최근 관련 헤드라인 뉴스]
{news_str}

아래 작성 가이드를 준수하여 텔레그램 메시지용 마크다운 형식으로 작성해 주세요.

[작성 가이드]
1. 📊 **투자의견 & 종합 평점**:
   - 투자의견: `🟢 매수 (Buy)`, `🟡 관망 (Hold)`, `🔴 매도/비중축소 (Sell/Trim)` 중 하나를 명확히 선택해 주세요.
   - 단기 매매 성향 평점(1~5점)을 매겨주세요.

2. 💡 **핵심 모멘텀 & 호재/악재 분석**:
   - 주가 흐름, 기술적 지표, 뉴스 이슈를 바탕으로 상승 모멘텀(호재) 및 리스크 요소(악재)를 각각 2줄 이내로 명확히 분석해 주세요.

3. 🎯 **권장 전략 & 목표가/손절가 제안**:
   - 신규 진입 및 기존 보유자를 위한 구체적인 대응 전략을 제시해 주세요.
   - 현재가 대비 적정 목표가 범위와 손절 기준가를 제시해 주세요.

시각적으로 깔끔하게 마크다운 기호(`*`, `•`, `🟢`, `🟡`, `🔴`, `🎯`)를 활용하여 핵심 위주로 명확하고 간결하게 작성해 주세요.
"""

    try:
        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
            )
        except Exception as model_err:
            if "404" in str(model_err) or "NOT_FOUND" in str(model_err):
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=prompt,
                )
            else:
                raise model_err

        ai_text = response.text.strip()
        
        result_msg = f"🤖 *[Gemini AI 종목 분석]* - *{name}* (`{ticker}`)\n"
        result_msg += f"💰 현재가: `{price_str}` ({pct_str})\n\n"
        result_msg += ai_text
        return result_msg
    except Exception as e:
        print(f"Error calling Gemini API for single stock analysis: {e}")
        err_str = str(e)
        if "API_KEY_INVALID" in err_str or "API key not valid" in err_str or "INVALID_ARGUMENT" in err_str:
            return (
                "⚠️ *Gemini API 키가 유효하지 않거나 설정되지 않았습니다.*\n\n"
                "구글 AI 스튜디오에서 무료 API 키를 발급받으신 후 텔레그램 창에 등록해 주세요:\n"
                "`/set_gemini [발급받은_API_KEY]`\n\n"
                "🔗 *무료 API 키 발급 받기:*\n"
                "https://aistudio.google.com/app/apikey"
            )
        return f"❌ *AI 분석 중 오류가 발생했습니다.*\n`{e}`"

